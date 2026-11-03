"""Sanitized local-only comparison of a retained lecture; never invokes an LLM.

Run inside the configured backend with --baseline-dir pointing to frozen source
files from the stated revision. Outputs counts/timings only, never lecture text.
"""

import argparse
import ast
import importlib.util
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from sqlalchemy import select, event
from app.core.config import settings
from app.db.database import get_session_factory, get_engine
from app.learner.factory import create_learner_engine
from app.learner.schemas import LearnerContextRequest
from app.files.factory import create_files
from app.rag.repositories.postgres import RAGRepository
from app.rag.repositories.tables import documents, versions
from app.rag.schemas import SearchRequest, ChatSelection
from app.rag.service import RAGService
from app.rag.document_reads import DocumentReads
from app.documents import create_document_reader


def main():
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--document", required=True)
    arguments.add_argument("--baseline-dir", type=Path, required=True)
    args = arguments.parse_args()
    sessions = get_session_factory()
    with sessions() as session:
        doc = dict(
            session.execute(
                select(documents).where(
                    documents.c.id == args.document, documents.c.deleted_at.is_(None)
                )
            )
            .mappings()
            .one()
        )
        version = dict(
            session.execute(
                select(versions)
                .where(versions.c.document_id == args.document)
                .order_by(versions.c.created_at.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
    owner = doc["learner_id"]
    files = create_files()
    service = RAGService(
        RAGRepository(sessions, files),
        create_learner_engine(),
        SimpleNamespace(),
        None,
        files,
        settings.model_copy(update={"rag_reranker_path": ""}),
    )
    source = ast.parse(
        (args.baseline_dir / "service.py").read_text(encoding="utf-8-sig")
    )
    method = next(
        node
        for cls in source.body
        if isinstance(cls, ast.ClassDef) and cls.name == "RAGService"
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "_eligible"
    )
    method.decorator_list = []
    from app.rag import service as current

    namespace = dict(vars(current), LearnerContextRequest=LearnerContextRequest)
    exec(
        compile(ast.Module(body=[method], type_ignores=[]), "frozen_scope", "exec"),
        namespace,
    )
    counter = [0]

    def count(*args):
        counter[0] += 1

    event.listen(get_engine(), "before_cursor_execute", count)
    report = {"baseline_revision": "51924b1", "live_llm_calls": 0, "scope": []}
    request = SearchRequest(query="OOP week 7 exception handling")
    for label, call in [
        ("before", lambda: namespace["_eligible"](service, owner, request)),
        ("after", lambda: service._eligible(owner, request)),
    ]:
        for repeat in range(3):
            counter[0] = 0
            start = perf_counter()
            _, eligible = call()
            report["scope"].append(
                dict(
                    implementation=label,
                    repeat=repeat,
                    elapsed_ms=round((perf_counter() - start) * 1000, 2),
                    sql_statements=counter[0],
                    eligible_documents=len(eligible),
                    target_eligible=any(row["id"] == doc["id"] for row in eligible),
                )
            )
    reader = create_document_reader(isolated=False)
    spec = importlib.util.spec_from_file_location(
        "frozen_pptx", args.baseline_dir / "pptx.py"
    )
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    report["extraction"] = []
    with files.materialize(owner, version["file_id"]) as path:
        for label, call in [
            ("before", lambda: old.PPTXReader(reader._vision).read(path, "pptx", 200)),
            ("after", lambda: reader.read_in_process(path, "pptx", 200)),
        ]:
            start = perf_counter()
            result = call()
            report["extraction"].append(
                dict(
                    implementation=label,
                    elapsed_ms=round((perf_counter() - start) * 1000, 2),
                    blocks=len(result["blocks"]),
                    characters=sum(len(block["text"]) for block in result["blocks"]),
                    visual_files=len(result.get("visuals", [])),
                    ocr_slides=sorted(
                        {
                            block["slide"]
                            for block in result["blocks"]
                            if block.get("method") == "image_ocr"
                        }
                    ),
                )
            )
    counter[0] = 0
    start = perf_counter()
    result = DocumentReads(service).read(owner, doc["id"], ChatSelection())
    report["ordered_read"] = dict(
        elapsed_ms=round((perf_counter() - start) * 1000, 2),
        sql_statements=counter[0],
        outline_sections=len(result["outline"]),
        source_chunks=len(result["retrieval"].chunks),
        next_offset=result["next_offset"],
        tokens=result["retrieval"].token_use,
    )
    import asyncio
    from app.langchain.workflow_tools import create_workflow_tools
    from app.history_management.budgets import ToolBudget

    budget = ToolBudget()
    tool = next(
        tool
        for tool in create_workflow_tools(owner, {"rag_service": service}, budget)
        if tool.name == "read_study_material"
    )
    receipt = asyncio.run(tool.ainvoke(dict(document_id=doc["id"])))
    budget.consume(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
    report["ordered_read"].update(
        receipt_bytes=budget.result_characters,
        receipt_tokens=budget.result_tokens,
        receipt_admitted=True,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
