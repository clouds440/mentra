import io
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import timedelta
from sqlalchemy import select, update
from qdrant_client import QdrantClient
from app.core.config import Settings
from app.core.exceptions import AppError
from app.rag.errors import ExtractionError
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest, ContextTransitionRequest
from app.rag.repositories.postgres import RAGRepository, now
from app.rag.repositories.tables import documents, jobs, generations
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.storage import FileStorage
from app.rag.service import RAGService
from app.rag.worker import IngestionWorker
from app.rag.schemas import SearchRequest, DocumentUpdate, RevisionRequest, AssessmentGroundingRequest, ChatSelection
from app.rag.vector_store import VectorChunk, VectorStoreError
from testing.postgres import PostgresSandbox
from testing.identities import TEST_LEARNERS, learner_id


class TestEmbedding:
    model_name, model_version, dimension, max_tokens = 'test', 'v1', 3, 512

    def token_count(self, text):
        return len(text.split()) + 2

    def query_token_count(self, text):
        return self.token_count(text)

    def embed_query(self, text):
        return [1., 0., 0.]

    def embed_documents(self, texts):
        return [[1., 0., 0.] for _ in texts]


class WorkflowTests(unittest.TestCase):
    def test_preextracted_chat_file_never_parses_again(self):
        extracted = dict(blocks=[dict(text='Python decorators wrap functions.', page=3, method='ocr')],
                         warnings=['OCR may contain errors.'], reader_revision='verified-reader', media_type='text/plain')
        with patch.object(self.service.parser, 'parse', side_effect=AssertionError('must reuse extraction')), \
             patch.object(self.service.parser, 'detect', side_effect=AssertionError('already detected')):
            result = self.service.accept_extracted(self.owner, source=io.BytesIO(b'original image bytes'),
                filename='notes.png', title='Notes', context_ids=[self.context.context_id], key='chat:one', extracted=extracted)
            self.assertTrue(self.worker.run_once())
            self.assertEqual(self.repo.get_job(self.owner, result['job_id'])['state'], 'SUCCEEDED')
            found = self.search()
            self.assertEqual(found.chunks[0].source.spans[0].page, 3)
            self.assertIn('OCR may contain errors.', found.chunks[0].source.warnings)
            replay = self.service.accept_extracted(self.owner, source=io.BytesIO(b'original image bytes'),
                filename='notes.png', title='Notes', context_ids=[self.context.context_id], key='chat:one', extracted=extracted)
            self.assertEqual(result['document_id'], replay['document_id'])

    def test_shared_reader_html_scripts_and_code_survive_rag_ingestion(self):
        cases = [('source.py', b'def decorators():\n    return "wrapper"\n', '    return "wrapper"'),
            ('notes.html', b'<h1>Decorators</h1><script>const decorators = "wrappers";</script><style>.decorators {color: red;}</style>', 'const decorators')]
        for filename, data, expected in cases:
            with self.subTest(filename=filename):
                accepted = self.service.accept_upload(self.owner, io.BytesIO(data), filename, filename,
                    [self.context.context_id], 'shared-' + filename)
                self.worker.run_once()
                self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'SUCCEEDED')
                result = self.service.search_document(self.owner, accepted['document_id'], 'decorators')
                self.assertTrue(any(expected in chunk.content for chunk in result.chunks))
                matched = next(chunk for chunk in result.chunks if expected in chunk.content)
                self.assertEqual(matched.source.filename, filename)
                self.assertEqual(matched.source.spans[0].language, 'py' if filename.endswith('.py') else 'js')
                passages = self.service.source_chunks(self.owner, accepted['document_id'], matched.source.version_id)
                self.assertTrue(all(chunk['filename'] == filename for chunk in passages))
                self.assertIn('py' if filename.endswith('.py') else 'css', {span.get('language') for chunk in passages for span in chunk['spans']})

    def test_cached_query_skips_duplicate_token_work_but_rechecks_changed_budget(self):
        from unittest.mock import Mock
        self.ready()
        self.embedding.query_token_count = Mock(return_value=12)
        with patch.object(self.embedding, 'token_count', side_effect=AssertionError('canonical chunk counts should be reused')):
            first = self.search()
            cached = self.search()
        self.assertEqual(first.token_use, cached.token_use)
        self.assertTrue(cached.diagnostics.query_cache_hit)
        self.embedding.query_token_count.assert_called_once_with('decorators')
        self.embedding.max_tokens = 8
        with self.assertRaises(AppError) as rejected:
            self.search()
        self.assertEqual(rejected.exception.code, 'RAG_QUERY_TOO_LONG')

    def test_library_batches_queries_and_preserves_failed_replacement_summary(self):
        from sqlalchemy import event
        first = self.ready()
        document = self.repo.get_document(self.owner, first['document_id'])
        self.upload(b'Replacement decorators source', key='replacement-summary', document_id=document['id'], expected_revision=document['revision'])
        with patch.object(self.service.parser, 'parse', side_effect=ExtractionError('invalid source')):
            self.worker.run_once()
        second = self.upload(b'Python dictionaries map keys to values.', key='second-summary')
        self.worker.run_once()
        statements = []
        def record(_connection, _cursor, statement, *_args):
            statements.append(statement)
        event.listen(self.db.engine, 'before_cursor_execute', record)
        try:
            result = self.repo.list_documents(self.owner)
        finally:
            event.remove(self.db.engine, 'before_cursor_execute', record)
        self.assertEqual(len(statements), 7)
        self.assertEqual(result['total'], 2)
        with self.db.sessions() as session:
            for item in result['items']:
                self.assertEqual(item, self.repo._detail(session, self.owner, item['id'], history_limit=1))
                self.assertNotIn('storage_key', item['versions'][0])
        summary = next(item for item in result['items'] if item['id'] == first['document_id'])
        self.assertEqual(summary['version_count'], 2)
        self.assertIn(first['generation_id'], [generation['id'] for generation in summary['generations']])
        self.assertEqual(self.repo.list_documents(self.other)['total'], 0)

    def test_vector_resume_fetch_is_batched_once_and_publication_still_rechecks(self):
        accepted = self.upload(b'Python decorators wrap functions. ' * 10000, key='large-batches')
        with patch.object(self.vector, 'indexed_chunk_ids', wraps=self.vector.indexed_chunk_ids) as identities, \
             patch.object(self.embedding, 'embed_documents', wraps=self.embedding.embed_documents) as embedding:
            self.worker.run_once()
        self.assertGreater(embedding.call_count, 1)
        self.assertEqual(identities.call_count, 2)
        self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'SUCCEEDED')

    def test_concept_scope_is_applied_before_dense_and_lexical_candidates(self):
        first = self.ready()
        other = self.upload(b'Database tables and unrelated SQL examples.', key='concept-distractor')
        self.worker.run_once()
        concept = self.learner.register_concept('Decorators')
        document = self.repo.get_document(self.owner, first['document_id'])
        self.service.tag_document(self.owner, document['id'], ['Decorators'], document['revision'])
        with patch.object(self.vector, 'query_chunks', wraps=self.vector.query_chunks) as dense, \
             patch.object(self.repo, 'lexical', wraps=self.repo.lexical) as lexical:
            result = self.search(mode='CONCEPT_FOCUSED', concept_ids=[concept.id])
        self.assertEqual(dense.call_args.args[1], [first['generation_id']])
        self.assertEqual(lexical.call_args.args[1], [first['generation_id']])
        self.assertTrue(result.chunks)
        self.assertTrue(all(chunk.source.document_id != other['document_id'] for chunk in result.chunks))

    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner, self.other = [learner_id(n) for n in TEST_LEARNERS[:2]]
        self.learner = LearnerEngine(self.db.repository)
        self.context = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Python', activate=True))
        self.settings = Settings(qdrant_url='http://test', qdrant_api_key='test', qdrant_collection='materials', rag_storage_dir=self.temp.name)
        self.client = QdrantClient(':memory:')
        self.embedding = TestEmbedding()
        self.vector = QdrantVectorStore(self.settings, self.embedding, self.client)
        self.addCleanup(self.vector.close)
        self.repo = RAGRepository(self.db.sessions)
        self.service = RAGService(self.repo, self.learner, self.embedding, self.vector, FileStorage(self.temp.name), self.settings)
        self.worker = IngestionWorker(self.service)

    def upload(self, content=b'Python decorators wrap functions. A decorator adds reusable behavior.', key='upload', **kwargs):
        return self.service.accept_upload(self.owner, io.BytesIO(content), 'notes.txt', 'Python Notes', [self.context.context_id], key, **kwargs)

    def search(self, **kwargs):
        return self.service.search(self.owner, SearchRequest(query='decorators', **kwargs))

    def ready(self):
        accepted = self.upload()
        self.assertTrue(self.worker.run_once())
        self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'SUCCEEDED')
        return accepted

    def test_upload_worker_search_source_and_identity(self):
        accepted = self.ready()
        result = self.search()
        self.assertEqual(result.status, 'ok')
        self.assertEqual(result.chunks[0].source.document_id, accepted['document_id'])
        self.assertEqual(result.chunks[0].source.spans[0].start, 0)
        source = result.chunks[0].source
        self.assertTrue(self.service.source(self.owner, source.document_id, source.version_id)[0].is_file())
        for action in (lambda: self.repo.get_document(self.other, source.document_id),
                       lambda: self.service.source(self.other, source.document_id, source.version_id),
                       lambda: self.repo.get_job(self.other, accepted['job_id'])):
            with self.assertRaises(AppError) as error:
                action()
            self.assertEqual(error.exception.status_code, 404)
        self.assertFalse(self.vector.query_chunks(self.other, [source.generation_id], [1,0,0], 10))

    def test_empty_scope_never_searches(self):
        self.ready()
        self.assertEqual(self.search(context_ids=[]).status, 'no_eligible_sources')
        self.assertEqual(self.search(document_ids=[]).status, 'no_eligible_sources')

    def test_idempotency_duplicate_and_conflict(self):
        first = self.upload()
        second = self.upload()
        self.assertEqual(first['job_id'], second['job_id'])
        self.assertEqual(len(list(Path(self.temp.name).iterdir())), 1)
        with self.assertRaises(AppError) as error:
            self.upload(b'different content')
        self.assertEqual(error.exception.code, 'RAG_IDEMPOTENCY_CONFLICT')
        third = self.upload(key='different-key')
        self.assertEqual(first['document_id'], third['document_id'])

    def test_failed_replacement_preserves_active_material(self):
        first = self.ready()
        doc = self.repo.get_document(self.owner, first['document_id'])
        second = self.upload(b'Valid first sixteen characters then \x00broken text', key='replacement', document_id=doc['id'], expected_revision=doc['revision'])
        self.worker.run_once()
        self.assertEqual(self.repo.get_job(self.owner, second['job_id'])['state'], 'FAILED')
        self.assertEqual(self.search().chunks[0].source.generation_id, first['generation_id'])

    def test_successful_replacement_switches_generation(self):
        first = self.ready()
        doc = self.repo.get_document(self.owner, first['document_id'])
        second = self.upload(b'Python decorators have a new explanation.', key='replacement', document_id=doc['id'], expected_revision=doc['revision'])
        self.worker.run_once()
        self.assertEqual(self.search().chunks[0].source.generation_id, second['generation_id'])
        old_version = doc['versions'][0]['id']
        self.assertTrue(self.service.source(self.owner, doc['id'], old_version)[0].exists())

    def test_archive_unarchive_and_context_policy(self):
        first = self.ready()
        doc = self.repo.get_document(self.owner, first['document_id'])
        doc = self.service.update_document(self.owner, doc['id'], DocumentUpdate(expected_revision=doc['revision'], archived=True))
        self.assertEqual(self.search().status, 'no_eligible_sources')
        self.assertTrue(self.search(mode='SOURCE_SPECIFIC', document_ids=[doc['id']], include_archived=True).chunks)
        self.service.update_document(self.owner, doc['id'], DocumentUpdate(expected_revision=doc['revision'], archived=False))
        self.assertTrue(self.search().chunks)
        self.learner.transition_context_state(ContextTransitionRequest(learner_id=self.owner, context_id=self.context.context_id, status='ARCHIVED', reason='test'))
        self.assertEqual(self.search(context_ids=[self.context.context_id]).status, 'no_eligible_sources')

    def test_delete_cancels_worker_and_purges(self):
        accepted = self.upload()
        job = self.repo.claim(300)
        self.repo.request_delete(self.owner, accepted['document_id'])
        with self.assertRaises(AppError):
            self.repo.publish(job)
        self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'CANCELLED')
        self.vector.ensure_collection()
        self.worker.run_once()
        self.assertFalse(list(Path(self.temp.name).iterdir()))
        self.assertEqual(self.repo.request_delete(self.owner, accepted['document_id'])['state'], 'purged')

    def test_expired_worker_is_fenced(self):
        accepted = self.upload()
        old = self.repo.claim(300)
        with self.db.sessions.begin() as session:
            session.execute(update(jobs).where(jobs.c.id == old['id']).values(lease_until=now() - timedelta(seconds=1)))
        new = self.repo.claim(300)
        self.assertNotEqual(old['lease_token'], new['lease_token'])
        with self.assertRaises(AppError):
            self.repo.stage(old, 'indexing', 300)
        self.repo.stage(new, 'parsing', 300)

    def test_revision_conflict_and_reindex(self):
        accepted = self.ready()
        doc = self.repo.get_document(self.owner, accepted['document_id'])
        with self.assertRaises(AppError):
            self.service.update_document(self.owner, doc['id'], DocumentUpdate(expected_revision=1, title='stale'))
        job = self.repo.reindex(self.owner, doc['id'], RevisionRequest(expected_revision=doc['revision'], idempotency_key='reindex'), self.service.config())
        self.worker.run_once()
        self.assertEqual(self.search().chunks[0].source.generation_id, job['generation_id'])

    def test_context_reassignment_uses_canonical_scope_before_payload_refresh(self):
        first = self.ready()
        new = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Another course'))
        doc = self.repo.get_document(self.owner, first['document_id'])
        self.service.update_document(self.owner, doc['id'], DocumentUpdate(expected_revision=doc['revision'], context_ids=[new.context_id]))
        self.assertEqual(self.search(context_ids=[self.context.context_id]).status, 'no_eligible_sources')
        self.assertTrue(self.search(context_ids=[new.context_id]).chunks)

    def test_delete_outage_and_late_write_reconciliation(self):
        first = self.ready()
        source = self.search().chunks[0].source
        self.repo.request_delete(self.owner, first['document_id'])
        with patch.object(self.vector, 'delete_chunks', side_effect=VectorStoreError('offline')):
            self.worker.run_once()
        self.assertEqual(self.search().status, 'no_eligible_sources')
        with self.assertRaises(AppError):
            self.service.source(self.owner, source.document_id, source.version_id)
        with self.db.sessions.begin() as session:
            session.execute(update(jobs).where(jobs.c.operation == 'DELETE').values(next_attempt_at=now()-timedelta(seconds=1)))
        self.worker.run_once()
        self.vector.upsert_chunks([VectorChunk(source.chunk_id, self.owner, source.document_id, source.generation_id,
                                              [self.context.context_id], [1,0,0])])
        with self.db.sessions.begin() as session:
            session.execute(update(generations).where(generations.c.id == source.generation_id).values(created_at=now()-timedelta(seconds=700)))
        self.worker.reconcile()
        self.assertEqual(self.vector.count_chunks(self.owner, source.generation_id), 0)

    def test_canonical_tags_and_unknown_labels_do_not_invent_ids(self):
        first = self.ready()
        concept = self.learner.register_concept('Decorators')
        doc = self.repo.get_document(self.owner, first['document_id'])
        tagged = self.service.tag_document(self.owner, doc['id'], ['Decorators', 'unknown-example-label'], doc['revision'])
        self.assertEqual(tagged['unresolved_labels'], ['unknown-example-label'])
        self.assertEqual(tagged['document']['concept_ids'], [concept.id])
        self.assertTrue(self.search(mode='CONCEPT_FOCUSED', concept_ids=[concept.id]).chunks)

    def test_optional_reranker_failure_is_explicit_and_scoped(self):
        self.ready()
        class Unavailable:
            def rank(self, *_args):
                return None
        self.service.reranker = Unavailable()
        result = self.search()
        self.assertEqual(result.status, 'degraded')
        self.assertTrue(result.warnings)
        self.assertTrue(result.chunks)

    def test_operator_rebuild_is_transactional_and_resumable(self):
        first = self.ready()
        run_id = str(__import__('uuid').uuid4())
        dry = self.repo.queue_rebuild(self.owner, run_id, self.service.config())
        self.assertEqual(dry['ready_materials'], 1)
        queued = self.repo.queue_rebuild(self.owner, run_id, self.service.config(), dry_run=False)
        self.worker.run_once()
        replay = self.repo.queue_rebuild(self.owner, run_id, self.service.config(), dry_run=False)
        self.assertEqual(queued['job_ids'], replay['job_ids'])

    def test_lexical_questions_match_identifiers_without_every_question_word(self):
        accepted = self.ready()
        ids = self.repo.lexical(self.owner, [accepted['generation_id']], 'What do decorators do?', 10)
        self.assertTrue(ids)
        self.assertEqual(self.repo.lexical(self.other, [accepted['generation_id']], 'decorators', 10), [])

    def test_old_citation_uses_exact_published_generation_after_reindex(self):
        accepted = self.ready()
        source = self.search().chunks[0].source
        doc = self.repo.get_document(self.owner, accepted['document_id'])
        self.repo.reindex(self.owner, doc['id'], RevisionRequest(expected_revision=doc['revision'], idempotency_key='new-index'), self.service.config())
        self.worker.run_once()
        old = self.service.source_chunks(self.owner, source.document_id, source.version_id, generation_id=source.generation_id)
        self.assertEqual(old[0]['id'], source.chunk_id)
        self.assertEqual(self.service.get_chunk(self.owner, source.chunk_id)['generation_id'], source.generation_id)
        self.assertEqual(self.service.source_chunks(self.owner, source.document_id, source.version_id, generation_id='missing'), [])
        with self.assertRaises(AppError):
            self.service.get_chunk(self.other, source.chunk_id)

    def test_archived_access_requires_explicit_scope(self):
        self.ready()
        with self.assertRaises(AppError) as raised:
            self.search(include_archived=True)
        self.assertEqual(raised.exception.code, 'RAG_SCOPE_REQUIRED')
        with self.assertRaises(AppError):
            self.search(mode='CONCEPT_FOCUSED')

    def test_library_context_filter_is_canonical(self):
        self.ready()
        self.assertEqual(self.repo.list_documents(self.owner, context_id=self.context.context_id)['total'], 1)
        self.assertEqual(self.repo.list_documents(self.owner, context_id='unrelated')['total'], 0)

    def test_operator_health_reports_owned_coverage_and_pending_lag(self):
        accepted = self.upload()
        queued = self.repo.index_health(self.owner)
        self.assertEqual(queued['job_states']['QUEUED'], 1)
        self.assertEqual(queued['active_generation_count'], 0)
        self.worker.run_once()
        ready = self.repo.index_health(self.owner)
        self.assertEqual(ready['active_generations'][0]['id'], accepted['generation_id'])
        self.assertEqual(ready['active_generation_count'], 1)
        self.assertEqual(self.repo.index_health(self.other)['active_generation_count'], 0)

    def test_duplicate_matching_does_not_substitute_a_different_latest_upload(self):
        original = b'Python decorators wrap functions. A decorator adds reusable behavior.'
        first = self.ready()
        doc = self.repo.get_document(self.owner, first['document_id'])
        self.upload(b'Revised Python source with different examples.', key='replacement', document_id=doc['id'], expected_revision=doc['revision'])
        self.worker.run_once()
        fresh = self.upload(original, key='old-content-as-new-material')
        self.assertFalse(fresh['duplicate'])
        self.assertNotEqual(fresh['document_id'], first['document_id'])
        history = self.repo.list_versions(self.owner, first['document_id'], offset=1, limit=1)
        self.assertEqual(history['total'], 2)
        self.assertEqual(history['items'][0]['generation_id'], first['generation_id'])
        with self.assertRaises(AppError):
            self.repo.list_versions(self.other, first['document_id'])

    def test_retry_resumes_persisted_chunks_without_repeating_ocr(self):
        accepted = self.upload()
        with patch.object(self.vector, 'upsert_chunks', side_effect=VectorStoreError('offline')):
            self.worker.run_once()
        self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'RETRY_WAIT')
        with self.db.sessions.begin() as session:
            session.execute(update(jobs).where(jobs.c.id == accepted['job_id']).values(next_attempt_at=now()-timedelta(seconds=1)))
        with patch.object(self.service.parser, 'parse', side_effect=AssertionError('checkpoint must avoid parsing again')):
            self.worker.run_once()
        self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'SUCCEEDED')
        self.assertTrue(self.search().chunks)

    def test_assessment_contract_requires_approved_owned_study_sources(self):
        accepted = self.ready()
        result = self.service.search_assessment(self.owner, AssessmentGroundingRequest(
            query='decorators', approved_document_ids=[accepted['document_id']]))
        self.assertEqual(result.mode, 'ASSESSMENT_GROUNDING')
        self.assertEqual(result.chunks[0].source.document_id, accepted['document_id'])
        with self.assertRaises(AppError):
            self.service.search_assessment(self.other, AssessmentGroundingRequest(
                query='decorators', approved_document_ids=[accepted['document_id']]))
        with self.assertRaises(__import__('pydantic').ValidationError):
            SearchRequest(query='decorators', mode='ASSESSMENT_GROUNDING')

    def test_bound_rag_tools_cannot_choose_identity_or_unseen_chunks(self):
        from app.langchain.rag_tools import create_rag_tools
        accepted = self.ready()
        search_tool, chunk_tool = create_rag_tools(self.service, self.owner, selection=ChatSelection(
            mode='SOURCE_SPECIFIC', document_ids=[accepted['document_id']]))
        with self.assertRaises(AppError):
            chunk_tool.invoke(dict(chunk_id='unseen'))
        with self.assertRaises(__import__('pydantic').ValidationError):
            search_tool.invoke(dict(query='decorators', learner_id=self.other))
        result = search_tool.invoke(dict(query='decorators'))
        chunk = chunk_tool.invoke(dict(chunk_id=result['chunks'][0]['source']['chunk_id']))
        self.assertEqual(chunk['learner_id'], self.owner)
        self.repo.request_delete(self.owner, accepted['document_id'])
        with self.assertRaises(AppError):
            chunk_tool.invoke(dict(chunk_id=chunk['id']))

    def test_retry_reuses_verified_vectors_after_publication_dependency_failure(self):
        accepted = self.upload()
        with patch.object(self.repo, 'publish', side_effect=RuntimeError('temporary dependency failure')):
            self.worker.run_once()
        self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'RETRY_WAIT')
        with self.db.sessions.begin() as session:
            session.execute(update(jobs).where(jobs.c.id == accepted['job_id']).values(next_attempt_at=now()-timedelta(seconds=1)))
        with patch.object(self.service.parser, 'parse', side_effect=AssertionError('do not reparse')), \
             patch.object(self.embedding, 'embed_documents', side_effect=AssertionError('do not reembed')):
            self.worker.run_once()
        self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'SUCCEEDED')

    def test_publication_requires_expected_point_ids_and_owner_payloads(self):
        accepted = self.upload()
        with patch.object(self.vector, 'indexed_chunk_ids', return_value=set()):
            self.worker.run_once()
        self.assertEqual(self.repo.get_job(self.owner, accepted['job_id'])['state'], 'RETRY_WAIT')
        self.assertIsNone(self.repo.get_document(self.owner, accepted['document_id'])['active_generation_id'])


if __name__ == '__main__':
    unittest.main()
