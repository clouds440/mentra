"""Source workflows and scoped retrieval, independent of FastAPI and LangChain."""
import hashlib
import json
from pathlib import Path
from threading import BoundedSemaphore
from collections import OrderedDict
import time
import logging
from uuid import uuid4
from app.core.exceptions import AppError
from app.learner.schemas import LearnerContextRequest, ConceptResolutionRequest
from app.learner.exceptions import LearningContextNotFoundError
from app.learner.services import LearnerService
from app.core.config import Settings
from app.rag.errors import ExtractionError, not_found
from app.rag.parsers import NativeDocumentParser
from app.rag.ports import DocumentParser, PrivateSourceStorage
from app.rag.processing import CHUNKER_VERSION, reciprocal_rank_fusion
from app.rag.schemas import RetrievalResult, RetrievedChunk, SourceReference, RetrievalDiagnostics, SearchRequest, AssessmentGroundingRequest
from app.rag.vector_store import VectorStoreError, VectorStore
from app.rag.embeddings import EmbeddingModelError, EmbeddingService


class RAGService:
    def __init__(self, repository, learner: LearnerService, embedding: EmbeddingService, vector_store: VectorStore,
                 storage: PrivateSourceStorage, settings: Settings, *, parser: DocumentParser | None = None):
        self.repository, self.learner, self.embedding = repository, learner, embedding
        self.vector_store, self.storage, self.settings = vector_store, storage, settings
        self.parser = parser or NativeDocumentParser()
        self._inference = BoundedSemaphore(1)
        self._query_cache = OrderedDict()
        self.reranker = None
        if settings.rag_reranker_path:
            from app.rag.reranker import LocalReranker
            self.reranker = LocalReranker(settings.rag_reranker_path, settings.rag_reranker_timeout)

    def close(self):
        if self.reranker:
            self.reranker.close()

    def config(self):
        return dict(parser=self.parser.version, chunker=CHUNKER_VERSION, embedding=self.embedding.model_name,
                    revision=self.embedding.model_version, dimension=self.embedding.dimension, index=self.vector_store.collection_name)

    def context_summaries(self, owner, context_ids=None):
        try:
            return self.learner.get_context_summaries(owner, context_ids)
        except LearningContextNotFoundError as exc:
            raise not_found() from exc

    def validate_contexts(self, owner, ids, allow_archived=False):
        ids = sorted(set(ids))
        if not 1 <= len(ids) <= 20:
            raise AppError('RAG_CONTEXT_REQUIRED', 'Choose between one and twenty learning contexts.', 422)
        contexts = self.context_summaries(owner, ids)
        if not allow_archived and any(c.status == 'ARCHIVED' for c in contexts):
            raise AppError('RAG_CONTEXT_ARCHIVED', 'Choose an available learning context.', 409)
        return ids

    def accept_upload(self, owner, file, filename, title, context_ids, key, document_id=None, expected_revision=None):
        filename = Path(filename.replace('\\', '/')).name[:200] or 'material'
        title = title.strip() or filename
        if len(title) > 200 or not 1 <= len(key) <= 120:
            raise AppError('RAG_INVALID_UPLOAD', 'Title or upload key exceeds the limit.', 422)
        contexts = self.validate_contexts(owner, context_ids)
        blob = self.storage.store(file, self.settings.rag_max_upload_bytes)
        retained = False
        try:
            blob['media_type'] = self.parser.detect(self.storage.path(blob['storage_key']), filename)
            fingerprint = hashlib.sha256(json.dumps(dict(hash=blob['file_hash'], title=title, contexts=contexts,
                target=document_id, revision=expected_revision), sort_keys=True).encode()).hexdigest()
            result = self.repository.accept(owner, title=title, filename=filename, context_ids=contexts,
                blob=blob, key=key, request_hash=fingerprint, config=self.config(), quota=self.settings.rag_storage_quota_bytes,
                document_id=document_id, expected_revision=expected_revision)
            retained = not result['duplicate']
            return result
        except ExtractionError as exc:
            raise AppError('RAG_UNSUPPORTED_FILE', str(exc), 422) from exc
        finally:
            if not retained:
                self.storage.remove(blob['storage_key'])

    def capabilities(self):
        return dict(**self.parser.capabilities(), max_upload_bytes=self.settings.rag_max_upload_bytes,
                    max_pages=self.settings.rag_max_pages, hybrid=self.settings.rag_hybrid_enabled,
                    reranking=self.reranker is not None, languages=['en'])

    def accept_extracted(self, owner, *, source, filename, title, context_ids, key, extracted):
        """Trusted service-only entry: reuse Documents output; never parse/OCR again.

        Original bytes remain the downloadable source. The immutable extraction
        snapshot travels with its version through ordinary chunk/embed/publication.
        HTTP/model callers cannot submit their own extraction payloads.
        """
        contexts = self.validate_contexts(owner, context_ids)
        if not extracted.get('blocks') or not extracted.get('reader_revision'):
            raise AppError('RAG_EMPTY_EXTRACTION', 'This file has no extracted content to save.', 422)
        blob = self.storage.store(source, self.settings.rag_max_upload_bytes)
        retained = False
        try:
            blob['media_type'] = extracted['media_type']
            blob['extracted_content'] = {name: extracted[name] for name in ('blocks', 'warnings', 'reader_revision')}
            fingerprint = hashlib.sha256(json.dumps(dict(hash=blob['file_hash'], contexts=contexts,
                title=title, extraction=blob['extracted_content']), sort_keys=True).encode()).hexdigest()
            result = self.repository.accept(owner, title=title[:200], filename=filename[:200], context_ids=contexts,
                blob=blob, key=key, request_hash=fingerprint, config=self.config(), quota=self.settings.rag_storage_quota_bytes)
            retained = not result['duplicate']
            return result
        finally:
            if not retained:
                self.storage.remove(blob['storage_key'])

    def get_document(self, owner, document_id):
        return self.repository.get_document(owner, document_id)

    def search_document(self, owner: str, document_id: str, query: str, *, include_archived: bool = False, limit: int = 8) -> RetrievalResult:
        return self.search(owner, SearchRequest(query=query, mode='SOURCE_SPECIFIC',
            document_ids=[document_id], include_archived=include_archived, limit=limit))

    def search_assessment(self, owner: str, request: AssessmentGroundingRequest) -> RetrievalResult:
        result = self.search(owner, SearchRequest(query=request.query, mode='SOURCE_SPECIFIC',
            document_ids=request.approved_document_ids, context_ids=request.context_ids,
            include_archived=request.include_archived, limit=request.limit))
        result.mode = 'ASSESSMENT_GROUNDING'
        return result

    def update_document(self, owner, document_id, request):
        if request.context_ids is not None:
            request.context_ids = self.validate_contexts(owner, request.context_ids)
        return self.repository.update_document(owner, document_id, request)

    def tag_document(self, owner, document_id, labels, expected_revision):
        doc = self.repository.get_document(owner, document_id)
        resolved, unresolved = [], []
        for label in dict.fromkeys(labels):
            resolution = self.learner.resolve_concept(ConceptResolutionRequest(label=label, learner_id=owner,
                context_id=doc['context_ids'][0]))
            if resolution.status == 'resolved' and resolution.concept_id:
                resolved.append(self.learner.get_concept(resolution.concept_id).id)
            else:
                unresolved.append(label)
        result = self.repository.tag_document(owner, document_id, expected_revision, sorted(set(resolved)))
        return dict(document=result, unresolved_labels=unresolved)

    def source(self, owner, document_id, version_id, include_archived=False):
        doc, version = self.repository.source(owner, document_id, version_id)
        self._source_policy(owner, doc, include_archived)
        path = self.storage.path(version['storage_key'])
        if not path.is_file():
            raise not_found()
        self.repository.record_usage(owner, [document_id])
        return path, version

    def _source_policy(self, owner, doc, include_archived):
        contexts = self.context_summaries(owner, doc['context_ids'])
        if not include_archived and (doc['archived'] or all(c.status == 'ARCHIVED' for c in contexts)):
            raise not_found()

    def source_chunks(self, owner, document_id, version_id, include_archived=False, offset=0, generation_id=None):
        doc, version = self.repository.source(owner, document_id, version_id)
        self._source_policy(owner, doc, include_archived)
        return [dict(row, filename=version['filename'], media_type=version['media_type']) for row in
                self.repository.source_chunks(owner, document_id, version_id, offset=offset, generation_id=generation_id)]

    def get_chunk(self, owner, chunk_id, include_archived=False):
        row = self.repository.get_chunk(owner, chunk_id)
        doc = self.repository.document_metadata(owner, [row['document_id']])[0]
        self._source_policy(owner, doc, include_archived)
        return row

    def _eligible(self, owner, request):
        if request.context_ids == [] or request.document_ids == []:
            return [], []
        if request.include_archived and not (request.context_ids or request.document_ids):
            raise AppError('RAG_SCOPE_REQUIRED', 'Select documents or contexts before including archived material.', 422)
        if request.mode == 'CONCEPT_FOCUSED' and not request.concept_ids:
            raise AppError('RAG_CONCEPT_REQUIRED', 'Choose canonical concepts to focus this search.', 422)
        if request.mode == 'SOURCE_SPECIFIC' and not request.document_ids:
            raise AppError('RAG_SOURCE_REQUIRED', 'Choose a source document.', 422)
        if request.mode == 'CROSS_CONTEXT' and not request.context_ids:
            raise AppError('RAG_CONTEXT_REQUIRED', 'Choose contexts to compare.', 422)
        selected = self.repository.document_metadata(owner, request.document_ids) if request.document_ids else []
        if request.context_ids is not None:
            contexts = self.context_summaries(owner, request.context_ids)
        elif request.document_ids:
            ids = sorted({c for doc in selected for c in doc['context_ids']})
            contexts = self.context_summaries(owner, ids)
        else:
            packet = self.learner.get_relevant_context(LearnerContextRequest(learner_id=owner, query=request.query))
            contexts = self.context_summaries(owner, packet.context_ids)
        ids = [c.context_id for c in contexts if request.include_archived or c.status != 'ARCHIVED']
        if not ids:
            return [], []
        return ids, self.repository.eligible(owner, ids, request.document_ids, request.include_archived)

    def search(self, owner: str, request: SearchRequest) -> RetrievalResult:
        started = checkpoint = time.monotonic()
        diagnostics = RetrievalDiagnostics(request_id=str(uuid4()))
        def mark(stage):
            nonlocal checkpoint
            stamp = time.monotonic()
            diagnostics.timings_ms[stage] = round((stamp - checkpoint) * 1000, 2)
            checkpoint = stamp
        if not request.query.strip():
            raise AppError('RAG_QUERY_REQUIRED', 'Enter a question to search.', 422)
        contexts, docs = self._eligible(owner, request)
        # Current canonical tags apply to every chunk of a material. Restrict
        # candidates before ranking so unrelated sources cannot crowd them out.
        if request.concept_ids:
            wanted = set(request.concept_ids)
            docs = [doc for doc in docs if wanted.intersection(doc['concept_ids'])]
        diagnostics.eligible_documents = len(docs)
        mark('scope')
        if request.concept_ids:
            request.concept_ids = [self.learner.get_concept(c).id for c in request.concept_ids]
            docs = [d for d in docs if set(request.concept_ids).intersection(d['concept_ids'])]
            diagnostics.eligible_documents = len(docs)
        if not docs:
            return RetrievalResult(status='no_eligible_sources', context_ids=contexts, diagnostics=diagnostics, mode=request.mode)
        generation_ids = [d['active_generation_id'] for d in docs]
        warnings = []
        try:
            with self._inference:
                cache_key = (owner, self.embedding.model_name, self.embedding.model_version,
                    self.embedding.dimension, self.embedding.max_tokens, request.query)
                cached = self._query_cache.get(cache_key)
                if cached and time.monotonic() - cached[0] < 60:
                    vector = cached[1]
                    diagnostics.query_cache_hit = True
                else:
                    if self.embedding.query_token_count(request.query) > self.embedding.max_tokens:
                        raise AppError('RAG_QUERY_TOO_LONG', 'Shorten this question to fit the retrieval model.', 422)
                    vector = self.embedding.embed_query(request.query)
                    self._query_cache[cache_key] = (time.monotonic(), vector)
                    while len(self._query_cache) > 128:
                        self._query_cache.popitem(last=False)
            mark('embedding')
            matches = self.vector_store.query_chunks(owner, generation_ids, vector, 80)
            diagnostics.dense_candidates = len(matches)
            mark('dense')
        except (VectorStoreError, EmbeddingModelError) as exc:
            raise AppError('RAG_UNAVAILABLE', 'Your study material is temporarily unavailable. Try again shortly.', 503) from exc
        dense = [m.id for m in matches]
        dense_ranks = {key: index + 1 for index, key in enumerate(dense)}
        lexical_ranks = {}
        ranked = [(m.id, m.score) for m in matches]
        score_type = 'dense_similarity'
        if self.settings.rag_hybrid_enabled:
            lexical = self.repository.lexical(owner, generation_ids, request.query, 80)
            lexical_ranks = {key: index + 1 for index, key in enumerate(lexical)}
            diagnostics.lexical_candidates = len(lexical)
            ranked = reciprocal_rank_fusion([dense, lexical])
            score_type = 'rrf'
        mark('fusion')
        rows = {r['id']: r for r in self.repository.hydrate(owner, [key for key, _ in ranked], generation_ids)}
        diagnostics.hydrated_candidates = len(rows)
        diagnostics.rejected_candidates = len(ranked) - len(rows)
        mark('hydration')
        if self.reranker:
            candidates = [(key, score) for key, score in ranked if key in rows][:40]
            scores = self.reranker.rank(request.query, [rows[key]['content'] for key, _ in candidates]) if candidates else []
            if scores is not None:
                ranked = sorted([(key, score) for (key, _), score in zip(candidates, scores, strict=True)], key=lambda item: (-item[1], item[0]))
                score_type = 'reranker'
                diagnostics.reranking = 'ok'
            else:
                diagnostics.reranking = 'fallback'
                warnings.append('Reranking was unavailable. Results use the original retrieval ranking.')
        mark('reranking')
        result, used, per_document, seen = [], 0, {}, set()
        ranked_positions = {key: index + 1 for index, (key, _) in enumerate(ranked)}
        doc_contexts = {d['id']: d['context_ids'] for d in docs}
        for key, score in ranked:
            row = rows.get(key)
            if not row or row['content_hash'] in seen or per_document.get(row['document_id'], 0) >= 4:
                continue
            if request.concept_ids and not set(request.concept_ids).intersection(row['concept_ids']):
                continue
            if used + row['token_count'] > request.token_budget:
                continue
            source = SourceReference(token=f'S{len(result)+1}', document_id=row['document_id'], version_id=row['version_id'],
                generation_id=row['generation_id'], chunk_id=key, title=row['title'], heading_path=row['heading_path'],
                filename=row.get('filename'), media_type=row.get('media_type'),
                spans=row['spans'], excerpt=row['content'], warnings=row['warnings'], include_archived=request.include_archived)
            result.append(RetrievedChunk(content=row['content'], score=score, score_type=score_type, source=source,
                context_ids=doc_contexts[row['document_id']], concept_ids=row['concept_ids'], dense_rank=dense_ranks.get(key),
                lexical_rank=lexical_ranks.get(key), reranker_rank=ranked_positions[key] if score_type == 'reranker' else None))
            used += row['token_count']
            seen.add(row['content_hash'])
            per_document[row['document_id']] = per_document.get(row['document_id'], 0) + 1
            if len(result) == request.limit:
                break
        # Re-authorize immediately before handing content to orchestration.
        _, current = self._eligible(owner, request)
        if request.concept_ids:
            current = [doc for doc in current if wanted.intersection(doc['concept_ids'])]
        current_generations = {d['active_generation_id'] for d in current}
        result = [r for r in result if r.source.generation_id in current_generations]
        current_by_generation = {d['active_generation_id']: d for d in current}
        for chunk in result:
            chunk.context_ids = current_by_generation[chunk.source.generation_id]['context_ids']
        self.repository.record_usage(owner, list({r.source.document_id for r in result}))
        mark('selection_and_reauthorization')
        diagnostics.timings_ms['total'] = round((time.monotonic() - started) * 1000, 2)
        logging.getLogger('mentra').info('RAG retrieval diagnostics: %s', diagnostics.model_dump())
        return RetrievalResult(chunks=result, status=('degraded' if warnings else 'ok') if result else 'no_matches', context_ids=contexts,
            warnings=warnings, token_use=sum(rows[r.source.chunk_id]['token_count'] for r in result), diagnostics=diagnostics, mode=request.mode)
