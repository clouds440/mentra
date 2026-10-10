"""Durable ingestion worker: python -m app.rag.worker. No in-request background jobs."""
import logging
import signal
import time
from app.core.exceptions import AppError
from app.rag.errors import ExtractionError
from app.rag.processing import chunk_blocks
from app.rag.vector_store import VectorChunk, VectorStoreError

logger = logging.getLogger('mentra')


from app.core.logging import workflow_logger

@workflow_logger.connect_module(ignore=('run_once',))
class IngestionWorker:
    def __init__(self, service):
        self.service = service
        self.repository = service.repository

    def stage(self, job, stage):
        self.repository.stage(job, stage, self.service.settings.rag_job_lease_seconds)
        workflow_logger.event('job.stage', job_id=job['id'], stage=stage, attempt=job['attempts'])
        logger.info('RAG job %s stage=%s attempt=%s', job['id'], stage, job['attempts'])

    def run_once(self):
        job = self.repository.claim(self.service.settings.rag_job_lease_seconds)
        if not job:
            return False
        with workflow_logger.workflow('rag.ingestion', log_context=job.get('log_context')) as execution:
            workflow_logger.event('job.claimed', job_id=str(job.get('id', job.get('turn_id', 'unknown'))), attempt=job.get('attempts', job.get('attempt', {}).get('worker_attempts', 1)) if isinstance(job.get('attempt'), dict) else job.get('attempts', job.get('attempt', 1)))
            started = time.monotonic()
            try:
                if job['operation'] == 'DELETE':
                    self.stage(job, 'deleting')
                    self.service.vector_store.delete_chunks(job['learner_id'], job['document_id'])
                    for key in self.repository.deletion_sources(job):
                        self.service.storage.remove(key)
                    self.repository.complete_delete(job)
                    execution.outcome = 'success'
                    return True
                self.stage(job, 'parsing')
                doc, generation, version = self.repository.work_source(job)
                if generation['config'] != self.service.config():
                    raise ExtractionError('The ingestion configuration changed. Reindex this material with the current model.')
                items = self.repository.resume_chunks(job, generation['chunk_count'])
                if items:
                    self.stage(job, 'resuming')
                else:
                    parsed = version.get('extracted_content')
                    if parsed is None:
                        parsed = self.service.parser.parse(self.service.storage.path(version['storage_key']), version['media_type'],
                            self.service.settings.rag_max_pages, self.service.settings.rag_parser_timeout)
                    else:
                        self.stage(job, 'reusing_extraction')
                    self.stage(job, 'chunking')
                    items = chunk_blocks(parsed['blocks'], self.service.embedding, job['learner_id'], job['document_id'],
                                         job['generation_id'], self.service.settings.rag_max_chunks, self.service.settings.rag_parser_timeout)
                    for item in items:
                        item['concept_ids'] = doc['concept_ids']
                    self.repository.save_chunks(job, items, parsed['warnings'])
                self.service.vector_store.initialize_chunk_indexes()
                self.stage(job, 'resuming_vectors')
                indexed = self.service.vector_store.indexed_chunk_ids(job['learner_id'], job['generation_id'], [c['id'] for c in items])
                for start in range(0, len(items), 32):
                    batch = items[start:start + 32]
                    batch = [chunk for chunk in batch if chunk['id'] not in indexed]
                    if not batch:
                        continue
                    self.stage(job, 'embedding')
                    vectors = self.service.embedding.embed_documents([c['content'] for c in batch])
                    self.stage(job, 'indexing')
                    self.service.vector_store.upsert_chunks([VectorChunk(c['id'], job['learner_id'], job['document_id'],
                        job['generation_id'], doc['context_ids'], v) for c, v in zip(batch, vectors, strict=True)])
                self.stage(job, 'verifying')
                if self.service.vector_store.count_chunks(job['learner_id'], job['generation_id']) != len(items):
                    raise VectorStoreError('Material index coverage is incomplete.')
                expected = {chunk['id'] for chunk in items}
                if self.service.vector_store.indexed_chunk_ids(job['learner_id'], job['generation_id'], list(expected)) != expected:
                    raise VectorStoreError('Material point identities are incomplete.')
                published = self.repository.publish(job)
                execution.outcome = 'success' if published else 'cancelled'
            except ExtractionError as exc:
                execution.outcome = 'failed'
                self.repository.fail(job, str(exc), False)
            except AppError as exc:
                execution.outcome = 'failed'
                if exc.code != 'RAG_LEASE_LOST':
                    self.repository.fail(job, exc.message, False)
            except Exception:
                execution.outcome = 'failed'
                logger.exception('RAG worker job failed: %s', job['id'])
                self.repository.fail(job, 'A processing dependency failed. Retry after the service recovers.', True)
            finally:
                logger.info('RAG job %s operation=%s elapsed_ms=%.2f', job['id'], job['operation'], (time.monotonic() - started) * 1000)
            return True

    def reconcile(self):
        self.repository.resume_cleanup()
        # Repeat after a full lease/parser window so late cancelled writes cannot
        # resurrect physical points. Eligibility never depends on this cleanup.
        age = max(self.service.settings.rag_job_lease_seconds * 2, self.service.settings.rag_parser_timeout * 2)
        for row in self.repository.reconciliation_targets(age):
            if row['id'] != row['active_generation_id']:
                self.service.vector_store.delete_chunks(row['learner_id'], row['document_id'], row['id'])
                self.repository.mark_reconciled(row['id'])
        self.service.storage.sweep_unknown(self.repository.storage_keys(), age)


def main():
    from app.core.config import settings
    from app.core.logging import configure_logging
    from app.db.database import init_db
    from app.learner.factory import create_learner_engine
    from app.rag.embeddings import SentenceTransformerEmbeddingService
    from app.rag.qdrant_store import QdrantVectorStore
    from app.rag.factory import create_rag_service
    configure_logging('rag-worker')
    init_db()
    embedding = SentenceTransformerEmbeddingService(settings)
    vector_store = QdrantVectorStore(settings, embedding)
    worker = IngestionWorker(create_rag_service(create_learner_engine(), embedding, vector_store))
    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_sweep = 0.0
    try:
        while not stopping:
            if not worker.run_once():
                time.sleep(1)
            if time.monotonic() - last_sweep > 60:
                try:
                    worker.reconcile()
                except Exception:
                    logger.exception('RAG reconciliation failed; next sweep will retry.')
                last_sweep = time.monotonic()
    finally:
        worker.service.close()
        vector_store.close()


if __name__ == '__main__':
    main()
