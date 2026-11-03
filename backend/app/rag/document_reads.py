"""Planner-directed catalog and sequential source reads, without inference."""

from collections import OrderedDict
from sqlalchemy import select, or_
from app.core.exceptions import AppError
from .schemas import SearchRequest, SourceReference, RetrievedChunk, RetrievalResult
from .repositories.tables import documents, chunks, generations
from .errors import not_found
from .visuals import Visuals


class DocumentReads:
    def __init__(self, service):
        self.service = service

    def eligible(self, owner, selection, identifier=None):
        request = SearchRequest(query="Library source access", **selection.model_dump())
        if identifier:
            if (
                selection.document_ids is not None
                and identifier not in selection.document_ids
            ):
                raise not_found()
            request.document_ids = [identifier]
        contexts, docs = self.service._eligible(owner, request)
        if identifier and not any(row["id"] == identifier for row in docs):
            raise not_found()
        return contexts, docs

    def find(self, owner, query, selection):
        _, docs = self.eligible(owner, selection)
        if not docs:
            return dict(items=[], has_more=False)
        terms = query.split()[:8]
        with self.service.repository.sessions() as session:
            statement = select(
                documents.c.id, documents.c.title, documents.c.filename
            ).where(
                documents.c.learner_id == owner,
                documents.c.id.in_([doc["id"] for doc in docs]),
            )
            for term in terms:
                statement = statement.where(
                    or_(
                        documents.c.title.icontains(term, autoescape=True),
                        documents.c.filename.icontains(term, autoescape=True),
                    )
                )
            rows = [
                dict(row)
                for row in session.execute(
                    statement.order_by(
                        documents.c.updated_at.desc(), documents.c.id
                    ).limit(13)
                ).mappings()
            ]
        return dict(items=rows[:12], has_more=len(rows) > 12)

    def read(self, owner, identifier, selection, offset=0, max_tokens=4000):
        contexts, docs = self.eligible(owner, selection, identifier)
        doc = next(row for row in docs if row["id"] == identifier)
        with self.service.repository.sessions() as session:
            source = (
                session.execute(
                    select(
                        generations.c.version_id,
                        generations.c.warnings,
                        documents.c.title,
                        documents.c.filename,
                    )
                    .join(documents, generations.c.document_id == documents.c.id)
                    .where(
                        generations.c.id == doc["active_generation_id"],
                        generations.c.learner_id == owner,
                    )
                )
                .mappings()
                .one()
            )
            rows = [
                dict(row)
                for row in session.execute(
                    select(chunks)
                    .where(
                        chunks.c.learner_id == owner,
                        chunks.c.generation_id == doc["active_generation_id"],
                    )
                    .order_by(chunks.c.ordinal)
                    .limit(5001)
                ).mappings()
            ]
        if len(rows) > 5000:
            raise AppError(
                "RAG_SCOPE_TOO_LARGE",
                "This source exceeds the sequential read limit.",
                422,
            )
        outline = OrderedDict()
        for row in rows:
            span = row["spans"][0]
            key = (span.get("page"), span.get("slide"), tuple(row["heading_path"]))
            section = outline.setdefault(
                key,
                dict(
                    page=key[0],
                    slide=key[1],
                    heading=row["heading_path"],
                    chunks=0,
                    has_visuals=False,
                ),
            )
            section["chunks"] += 1
            section["has_visuals"] |= bool(span.get("visual_keys"))
        # Outline supplies headings; avoid spending most of the evidence budget
        # on heading-only chunks instead of the lecture's substantive content.
        bodies = [
            row
            for row in rows
            if not row["heading_path"]
            or row["content"].strip() != row["heading_path"][-1].strip()
        ]
        if not bodies:
            bodies = rows
        chosen = []
        used = 0
        next_offset = None
        for index, row in enumerate(bodies[offset:], offset):
            if used + row["token_count"] > max_tokens or len(chosen) >= 64:
                next_offset = index
                break
            chosen.append(row)
            used += row["token_count"]
        if not chosen and offset < len(bodies):
            raise AppError(
                "RAG_READ_BUDGET",
                "Increase the read budget to include this passage.",
                422,
            )
        media = Visuals(
            self.service.repository, self.service.files, self.service.settings
        ).for_chunks(owner, chosen)
        result = []
        for row in chosen:
            ref = SourceReference(
                token="",
                document_id=identifier,
                version_id=source["version_id"],
                generation_id=doc["active_generation_id"],
                chunk_id=row["id"],
                title=source["title"],
                filename=source["filename"],
                heading_path=row["heading_path"],
                spans=row["spans"],
                excerpt=row["content"],
                warnings=source["warnings"],
                visuals=media.get(row["id"], []),
                include_archived=selection.include_archived,
            )
            result.append(
                RetrievedChunk(
                    content=row["content"],
                    score=1,
                    score_type="source_order",
                    source=ref,
                    context_ids=doc["context_ids"],
                )
            )
        # Current ownership, archive state and published generation are rechecked.
        _, current = self.eligible(owner, selection, identifier)
        if not any(
            row["active_generation_id"] == doc["active_generation_id"]
            for row in current
        ):
            raise AppError(
                "RAG_CONFLICT",
                "This source changed while reading. Read the current version again.",
                409,
            )
        return dict(
            outline=list(outline.values())[:200],
            outline_truncated=len(outline) > 200,
            next_offset=next_offset,
            total_chunks=len(rows),
            retrieval=RetrievalResult(
                status="ok" if result else "no_matches",
                chunks=result,
                context_ids=contexts,
                token_use=used,
                mode="SOURCE_SPECIFIC",
            ),
        )
