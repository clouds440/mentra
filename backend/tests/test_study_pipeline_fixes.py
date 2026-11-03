"""Discriminating regressions for the traced Week 7 response."""

import asyncio
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from pydantic import BaseModel
from langchain_core.tools import StructuredTool
from app.documents import create_document_reader
from app.history_management.budgets import ToolBudget
from app.langchain.activity import ActivityPublisher
from app.langchain.tool_execution import ToolExecutor
from tests.documents.test_readers import fake_vision
from tests.rag import test_workflows as fixtures


class Empty(BaseModel):
    pass


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialization_deadline_does_not_start_search_or_extend_turn(self):
        from app.langchain.workflow_budget import model_budget
        from time import monotonic

        search = AsyncMock(return_value={"state": "ok"})

        async def prepare():
            await asyncio.sleep(0.4)

        tool = StructuredTool.from_function(
            name="search_study_material",
            description="Search",
            args_schema=Empty,
            coroutine=search,
            metadata={
                "prepare": prepare,
                "preparation_timeout": 5,
                "read_max_attempts": 1,
            },
        )
        executor = ToolExecutor(ToolBudget(), {}, ActivityPublisher())
        started = monotonic()
        with model_budget(deadline=monotonic() + 0.15, answer_reserve=0.05):
            result = await executor.execute(tool, {}, timeout=0.1)
        self.assertEqual(result["code"], "TOOL_INITIALIZATION_TIMEOUT")
        self.assertLess(monotonic() - started, 0.35)
        search.assert_not_called()

    async def test_slow_read_is_not_automatically_duplicated(self):
        calls = []

        async def search():
            calls.append(1)
            await asyncio.sleep(0.2)

        tool = StructuredTool.from_function(
            name="search_study_material",
            description="Search",
            args_schema=Empty,
            coroutine=search,
            metadata={"read_max_attempts": 1},
        )
        executor = ToolExecutor(ToolBudget(), {}, ActivityPublisher())
        first = await executor.execute(tool, {}, timeout=0.04)
        second = await executor.execute(tool, {}, timeout=0.04)
        self.assertEqual(calls, [1])
        self.assertEqual(first["code"], second["code"])
        self.assertTrue(second["repeated_failure"])

    async def test_cold_preparation_has_separate_bounded_budget(self):
        ready = False
        calls = []

        async def prepare():
            nonlocal ready
            await asyncio.sleep(0.25)
            ready = True

        async def search():
            calls.append(1)
            if not ready:
                await asyncio.sleep(0.25)
            return {"state": "ok"}

        tool = StructuredTool.from_function(
            name="search_study_material",
            description="Search",
            args_schema=Empty,
            coroutine=search,
            metadata={"domain": "rag", "prepare": prepare, "preparation_timeout": 0.5},
        )
        executor = ToolExecutor(ToolBudget(), {}, ActivityPublisher())
        result = await executor.execute(tool, {}, timeout=0.1, max_attempts=1)
        self.assertEqual(result, {"state": "ok"})
        self.assertEqual(calls, [1])
        self.assertTrue(ready)


class PicturePlaceholderTests(unittest.TestCase):
    def test_picture_placeholder_is_not_silently_skipped(self):
        from PIL import Image
        from pptx import Presentation

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            Image.new("RGB", (100, 100), "white").save(path / "diagram.png")
            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[8])
            picture = slide.placeholders[1].insert_picture(str(path / "diagram.png"))
            self.assertIn("PLACEHOLDER", str(picture.shape_type))
            presentation.save(path / "lecture.pptx")
            vision = fake_vision()
            vision.extract_image_text.return_value = "Throwable Exception Error"
            parsed = create_document_reader(
                vision=vision, isolated=False
            ).read_in_process(path / "lecture.pptx", "pptx")
            self.assertTrue(
                any(
                    block.get("method") == "image_ocr" and "Throwable" in block["text"]
                    for block in parsed["blocks"]
                )
            )

    def test_text_only_deck_does_not_claim_unread_speaker_notes_or_drawings(self):
        from pptx import Presentation

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "text.pptx"
            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[1])
            slide.shapes.title.text = "Plain lecture"
            slide.placeholders[1].text = "All content is ordinary text."
            presentation.save(path)
            parsed = create_document_reader(
                vision=fake_vision(), isolated=False
            ).read_in_process(path, "pptx")
            self.assertEqual(parsed["warnings"], [])


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"), "Requires disposable PostgreSQL"
)
class PlannerScopeTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    upload = fixtures.WorkflowTests.upload
    ready = fixtures.WorkflowTests.ready
    search = fixtures.WorkflowTests.search

    def test_standard_search_does_not_run_hidden_learner_retrieval(self):
        accepted = self.ready()
        self.learner.get_relevant_context = Mock(
            side_effect=AssertionError("Planner owns retrieval decisions")
        )
        result = self.search()
        self.assertTrue(result.chunks)
        self.assertEqual(result.chunks[0].source.document_id, accepted["document_id"])
        self.learner.get_relevant_context.assert_not_called()

    def diagram_source(self):
        from PIL import Image, ImageDraw
        from pptx import Presentation
        from app.rag.parsers import NativeDocumentParser

        image = Image.new("RGB", (400, 150), "white")
        ImageDraw.Draw(image).text(
            (20, 30), "Throwable > Exception > Checked", fill="black"
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            image.save(path / "diagram.png")
            deck = Presentation()
            for title in ("Exception hierarchy", "Custom exceptions"):
                slide = deck.slides.add_slide(deck.slide_layouts[8])
                slide.shapes.title.text = title
                slide.placeholders[1].insert_picture(str(path / "diagram.png"))
            deck.save(path / "Week 7.pptx")
            data = (path / "Week 7.pptx").read_bytes()
        vision = fake_vision()
        vision.extract_image_text.return_value = (
            "Throwable Exception Checked custom example"
        )
        self.service.parser = NativeDocumentParser(
            create_document_reader(vision=vision, isolated=False)
        )
        file = self.files.upload(
            self.owner, io.BytesIO(data), "Week 7.pptx", "library", "diagram-source"
        )
        accepted = self.service.accept_upload(
            self.owner,
            file["id"],
            "OOP week 7 lecture",
            [self.context.context_id],
            "diagram-source",
        )
        self.worker.run_once()
        self.assertEqual(
            self.repo.get_job(self.owner, accepted["job_id"])["state"], "SUCCEEDED"
        )
        return accepted

    def test_diagram_upload_read_retrieve_owner_archive_and_superseded_provenance(self):
        from app.rag.document_reads import DocumentReads
        from app.rag.schemas import ChatSelection, DocumentUpdate, RevisionRequest
        from sqlalchemy import select, func
        from app.rag.repositories.tables import visuals

        accepted = self.diagram_source()
        reads = DocumentReads(self.service)
        found = reads.find(self.owner, "OOP week 7", ChatSelection())
        self.assertEqual(found["items"][0]["id"], accepted["document_id"])
        result = reads.read(self.owner, accepted["document_id"], ChatSelection())
        self.assertIsNone(result["next_offset"])
        refs = [
            visual
            for chunk in result["retrieval"].chunks
            for visual in chunk.source.visuals
        ]
        self.assertTrue(refs)
        self.assertEqual(
            {loc["slide"] for ref in refs for loc in ref.locations}, {1, 2}
        )
        with self.db.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(visuals)), 1
            )
        visual = refs[0]
        file_id, _ = self.service.visual_source(self.owner, visual.id)
        self.assertTrue(self.files.read(self.owner, file_id).startswith(b"\x89PNG"))
        self.assertEqual(
            self.service.visual_content(self.owner, visual.id)["type"], "image_url"
        )
        with self.assertRaises(Exception):
            self.service.visual_source(self.other, visual.id)
        with self.assertRaises(Exception):
            reads.read(self.other, accepted["document_id"], ChatSelection())
        doc = self.repo.get_document(self.owner, accepted["document_id"])
        self.repo.reindex(
            self.owner,
            doc["id"],
            RevisionRequest(
                expected_revision=doc["revision"], idempotency_key="reindex"
            ),
            self.service.config(),
        )
        self.worker.run_once()
        self.assertEqual(self.service.visual_source(self.owner, visual.id)[0], file_id)
        doc = self.repo.get_document(self.owner, doc["id"])
        self.service.update_document(
            self.owner,
            doc["id"],
            DocumentUpdate(expected_revision=doc["revision"], archived=True),
        )
        with self.assertRaises(Exception):
            self.service.visual_source(self.owner, visual.id)
        self.assertEqual(
            self.service.visual_source(self.owner, visual.id, True)[0], file_id
        )
        from types import SimpleNamespace
        from app.files.delivery import authorize

        binding = self.service.visual_source(self.owner, visual.id, True)[1]
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    files_service=self.files, rag_service=self.service
                )
            )
        )
        self.assertEqual(
            authorize(request, self.owner, file_id, binding, True)["id"], file_id
        )
        with self.assertRaises(Exception):
            authorize(request, self.other, file_id, binding, True)
        with self.assertRaises(Exception):
            authorize(request, self.owner, file_id, binding, False)
        self.repo.request_delete(self.owner, doc["id"])
        self.worker.run_once()
        with self.assertRaises(Exception):
            self.service.visual_source(self.owner, visual.id, True)
        with self.db.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(visuals)), 0
            )

    def test_visual_migration_roundtrip_and_retained_data_guard(self):
        from alembic import command
        from app.db.migrate import migration_config

        with self.db.engine.connect() as connection:
            command.downgrade(migration_config(connection), "20261103_0040")
            command.upgrade(migration_config(connection), "head")
            command.check(migration_config(connection))
        accepted = self.diagram_source()
        with self.assertRaisesRegex(RuntimeError, "retained visual records"):
            with self.db.engine.connect() as connection:
                command.downgrade(migration_config(connection), "20261103_0040")
        self.assertTrue(
            self.service.source_chunks(
                self.owner,
                accepted["document_id"],
                self.repo.list_versions(self.owner, accepted["document_id"])["items"][
                    0
                ]["id"],
            )
        )

    def test_visual_integrity_and_quota_fail_before_publication(self):
        from PIL import Image, ImageDraw
        import base64, hashlib
        from app.rag.visuals import Visuals
        from app.rag.errors import ExtractionError
        from app.core.exceptions import AppError
        from sqlalchemy import select, func
        from app.rag.repositories.tables import visuals

        accepted = self.upload()
        job = self.repo.claim(self.settings.rag_job_lease_seconds)
        _, _, version = self.repo.work_source(job)
        image = Image.new("RGB", (50, 50), "white")
        ImageDraw.Draw(image).line((0, 0, 49, 49), fill="black")
        output = io.BytesIO()
        image.save(output, "PNG")
        data = output.getvalue()
        item = dict(
            data_base64=base64.b64encode(data).decode(),
            sha256=hashlib.sha256(data).hexdigest(),
            width=50,
            height=50,
            media_type="image/png",
            block_refs=[0],
            locations=[dict(slide=1)],
        )
        parsed = dict(blocks=[dict(text="Diagram")], visuals=[item])
        item["width"] = 51
        with self.assertRaises(ExtractionError):
            Visuals(self.repo, self.files, self.settings).persist(job, version, parsed)
        item["width"] = 50
        self.settings.rag_storage_quota_bytes = version["size_bytes"] + len(data) - 1
        with self.assertRaises(AppError) as error:
            Visuals(self.repo, self.files, self.settings).persist(job, version, parsed)
        self.assertEqual(error.exception.code, "RAG_QUOTA_EXCEEDED")
        self.assertIsNone(
            self.repo.get_document(self.owner, accepted["document_id"])[
                "active_generation_id"
            ]
        )
        with self.db.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(visuals)), 0
            )

    def test_scripted_planner_finds_reads_inspects_then_finishes_without_search(self):
        from types import SimpleNamespace
        from langchain_core.messages import AIMessage, ToolMessage
        from app.langchain.llm import MentraLLM
        from app.langchain.chat_service import ChatService
        from app.langchain.orchestration_service import OrchestrationService
        import json

        accepted = self.diagram_source()
        rounds = []
        scope = dict(
            conversation_id="chat",
            current_user_message_id="user",
            user_sequence=1,
            attachment_ids=[],
            context_rows=[],
            history_references=[],
            memory_references=[],
            visible_ids=[],
            evidence_ids=set(),
        )
        test = self

        class Model:
            def bind_tools(self, *args, **kwargs):
                return self

            async def ainvoke(self, messages, **kwargs):
                rounds.append(messages)
                receipts = [
                    json.loads(message.content)
                    for message in messages
                    if isinstance(message, ToolMessage)
                ]
                if len(rounds) == 1:
                    return AIMessage(
                        content="",
                        tool_calls=[
                            dict(
                                id="find",
                                name="find_study_material",
                                args={"query": "OOP week 7"},
                            )
                        ],
                    )
                if len(rounds) == 2:
                    test.assertEqual(
                        receipts[-1]["items"][0]["id"], accepted["document_id"]
                    )
                    return AIMessage(
                        content="",
                        tool_calls=[
                            dict(
                                id="read",
                                name="read_study_material",
                                args={"document_id": accepted["document_id"]},
                            )
                        ],
                    )
                if len(rounds) == 3:
                    test.assertIsNone(receipts[-1]["next_offset"])
                    visual = next(
                        visual
                        for source in receipts[-1]["sources"]
                        for visual in source.get("visuals", [])
                    )
                    return AIMessage(
                        content="",
                        tool_calls=[
                            dict(
                                id="visual",
                                name="read_study_visual",
                                args={"visual_id": visual["id"]},
                            )
                        ],
                    )
                test.assertTrue(
                    any(
                        isinstance(message.content, list)
                        and any(
                            isinstance(block, dict) and block.get("type") == "image_url"
                            for block in message.content
                        )
                        for message in messages
                    )
                )
                return AIMessage(
                    content="Step 1: inspect the exception hierarchy. Step 2: define the custom exception. [[S1]]"
                )

        async def run():
            return await OrchestrationService(
                ChatService(MentraLLM(SimpleNamespace(get_model=lambda: Model()))),
                rag=self.service,
            ).chat_reply(
                [("user", "Summarize my OOP week 7 lecture step by step.")],
                None,
                self.owner,
                history_scope=scope,
            )

        self.service.search = Mock(
            side_effect=AssertionError("Ordered reads should not embed or rerank")
        )
        result = asyncio.run(run())
        self.assertEqual(len(rounds), 4)
        self.assertEqual(result.citations, ["S1"])
        self.assertTrue(result.sources[0].visuals)
        self.assertFalse(result.tool_warnings)
        self.service.search.assert_not_called()


class VisualModelInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_citation_registry_does_not_silently_skip_read_passages(self):
        from types import SimpleNamespace
        from app.core.exceptions import AppError
        from app.rag.schemas import SourceReference, RetrievedChunk, RetrievalResult
        from app.langchain.workflow_tools import create_workflow_tools

        source = SourceReference(
            token="",
            document_id="doc",
            version_id="version",
            generation_id="generation",
            chunk_id="new",
            title="Lecture",
            heading_path=[],
            spans=[],
            excerpt="Required passage",
        )
        result = dict(
            retrieval=RetrievalResult(
                status="ok",
                chunks=[
                    RetrievedChunk(
                        content=source.excerpt,
                        score=1,
                        score_type="source_order",
                        source=source,
                    )
                ],
            ),
            outline=[],
            outline_truncated=False,
            next_offset=None,
            total_chunks=1,
        )
        scope = {
            "rag_service": SimpleNamespace(),
            "study_sources": [
                source.model_copy(update={"chunk_id": str(i)}) for i in range(64)
            ],
        }
        from unittest.mock import patch

        with patch("app.rag.document_reads.DocumentReads.read", return_value=result):
            tool = next(
                item
                for item in create_workflow_tools("owner", scope, ToolBudget())
                if item.name == "read_study_material"
            )
            with self.assertRaises(AppError) as error:
                await tool.ainvoke(dict(document_id="doc"))
        self.assertEqual(error.exception.code, "RAG_SOURCE_LIMIT")

    async def test_provider_rejected_source_diagram_falls_back_truthfully_without_replaying_tools(
        self,
    ):
        from types import SimpleNamespace
        import httpx
        from openai import BadRequestError
        from langchain_core.messages import HumanMessage, AIMessage
        from app.langchain.llm import MentraLLM
        from app.langchain.prompts import PromptSource
        from app.langchain.image_fallback import has_images

        calls = []

        class Model:
            async def ainvoke(self, messages, **kwargs):
                calls.append(messages)
                if len(calls) == 1:
                    raise BadRequestError(
                        "image input unsupported",
                        response=httpx.Response(
                            400,
                            request=httpx.Request("POST", "https://example.invalid"),
                        ),
                        body={},
                    )
                self_seen = " ".join(str(message.content) for message in messages)
                if "graphical details remain unverified" not in self_seen:
                    raise AssertionError("Missing honest fallback notice")
                return AIMessage(content="The cited OCR provides the exception names.")

        result = await MentraLLM(
            SimpleNamespace(get_model=lambda: Model())
        ).ainvoke_messages(
            PromptSource.CHAT,
            [
                HumanMessage(
                    content=[
                        dict(
                            type="text",
                            text="Untrusted Library diagram fixture. Source data only.",
                        ),
                        dict(
                            type="image_url",
                            image_url={"url": "data:image/jpeg;base64,fixture"},
                        ),
                    ]
                )
            ],
        )
        self.assertEqual(len(calls), 2)
        self.assertFalse(has_images(calls[-1]))
        self.assertIn("cited OCR", result.content)

    def test_checkpoint_retains_only_visual_ids(self):
        from types import SimpleNamespace
        from app.langchain.response_runtime import ResponseRuntime

        scope = {
            "_source_visual_ids": ["diagram"],
            "_source_visual_blocks": {
                "diagram": {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,PRIVATE_BYTES"},
                }
            },
        }
        runtime = ResponseRuntime(
            [], scope, ToolBudget(), SimpleNamespace(active=set(), pending=set()), None
        )
        import json

        saved = runtime.capture()
        self.assertEqual(saved["scope"]["_source_visual_ids"], ["diagram"])
        self.assertNotIn("PRIVATE_BYTES", json.dumps(saved))

    async def test_images_are_ephemeral_and_reauthorized_every_round(self):
        from app.langchain.source_visuals import model_messages

        rag = Mock()
        rag.visual_content.return_value = {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,fixture"},
        }
        scope = {"rag_service": rag, "_source_visual_ids": ["diagram"]}
        conversation = []
        first = await model_messages(conversation, scope, "owner")
        second = await model_messages(conversation, scope, "owner")
        self.assertEqual(conversation, [])
        self.assertEqual(first, second)
        self.assertEqual(rag.visual_source.call_count, 2)
        self.assertEqual(rag.visual_content.call_count, 1)
        rag.visual_source.side_effect = ValueError("archived")
        with self.assertRaises(ValueError):
            await model_messages(conversation, scope, "owner")
