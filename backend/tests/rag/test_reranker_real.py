"""Opt-in real CPU reranker + E5 + RAG pipeline in disposable PostgreSQL/Qdrant.

Requires TEST_DATABASE_URL, TEST_RERANKER_PATH and TEST_EMBEDDING_PATH.
RERANKER_TEST_REPORT optionally saves a synthetic, content-free JSON result.
"""
import io
import json
import os
import time
import unittest
from pathlib import Path

from qdrant_client import QdrantClient
from app.core.config import Settings
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest
from app.rag.embeddings import SentenceTransformerEmbeddingService
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.repositories.postgres import RAGRepository
from app.rag.schemas import SearchRequest
from app.rag.service import RAGService
from app.rag.worker import IngestionWorker
from scripts.verify_multilingual_embeddings import PASSAGES, QUERIES
from testing.files import create_test_files
from testing.identities import TEST_LEARNERS, learner_id
from testing.postgres import PostgresSandbox


@unittest.skipUnless(all(os.environ.get(key) for key in (
    'TEST_DATABASE_URL', 'TEST_RERANKER_PATH', 'TEST_EMBEDDING_PATH')), 'Requires disposable DB and real local models')
class RealRerankerTests(unittest.TestCase):
    def test_multilingual_ingestion_search_reranking_and_fallback(self):
        with PostgresSandbox() as database:
            settings = Settings(_env_file=None, embedding_model='intfloat/multilingual-e5-small',
                embedding_device='cpu', qdrant_url='http://test', qdrant_api_key='test',
                qdrant_collection='reranker-test', rag_reranker_path=os.environ['TEST_RERANKER_PATH'])
            embedding = SentenceTransformerEmbeddingService(settings, model_path=Path(os.environ['TEST_EMBEDDING_PATH']))
            vector = QdrantVectorStore(settings, embedding, QdrantClient(':memory:'))
            self.addCleanup(vector.close)
            files = create_test_files(database.sessions, settings)
            self.addCleanup(files.close)
            learner = LearnerEngine(database.repository)
            owner = learner_id(TEST_LEARNERS[0])
            context = learner.resolve_learning_context(ResolveLearningContextRequest(
                learner_id=owner, name='Synthetic science', activate=True))
            repository = RAGRepository(database.sessions, files)
            service = RAGService(repository, learner, embedding, vector, files, settings)
            self.addCleanup(service.close)
            worker = IngestionWorker(service)
            documents = {}
            for language, passages in PASSAGES.items():
                documents[language] = []
                for topic, content in enumerate(passages):
                    key = f'{language}-{topic}'
                    file = files.upload(owner, io.BytesIO(content.encode('utf-8')), key + '.txt', 'library', 'file:' + key)
                    accepted = service.accept_upload(owner, file['id'], key, [context.context_id], key)
                    self.assertTrue(worker.run_once())
                    self.assertEqual(repository.get_job(owner, accepted['job_id'])['state'], 'SUCCEEDED')
                    documents[language].append(accepted['document_id'])
            results, rank_seconds = [], []
            process = None
            for query_language, queries in QUERIES.items():
                for topic, query in enumerate(queries):
                    for corpus_language, passages in PASSAGES.items():
                        started = time.monotonic()
                        scores = service.reranker.rank(query, passages)
                        rank_seconds.append(round(time.monotonic() - started, 4))
                        self.assertIsNotNone(scores)
                        actual = max(range(len(scores)), key=scores.__getitem__)
                        result = service.search(owner, SearchRequest(query=query, mode='SOURCE_SPECIFIC',
                            document_ids=documents[corpus_language], limit=3))
                        pipeline_topic = documents[corpus_language].index(result.chunks[0].source.document_id)
                        results.append(dict(query_language=query_language, corpus_language=corpus_language,
                            expected=topic, reranker_top1=actual, pipeline_top1=pipeline_topic,
                            reranking=result.diagnostics.reranking))
                        self.assertEqual(result.diagnostics.reranking, 'ok')
                        self.assertEqual(result.status, 'ok')
                        self.assertTrue(all(chunk.source.document_id in documents[corpus_language] for chunk in result.chunks))
                        if process is None:
                            process = service.reranker._process
                        self.assertIs(service.reranker._process, process)
            service.reranker.close()
            fallback = service.search(owner, SearchRequest(query=QUERIES['en'][0], mode='SOURCE_SPECIFIC',
                document_ids=documents['en']))
            self.assertEqual(fallback.diagnostics.reranking, 'fallback')
            self.assertEqual(fallback.status, 'degraded')
            self.assertTrue(fallback.chunks)
            identity = json.loads((Path(settings.rag_reranker_path) / 'model-metadata.json').read_text())
            report = dict(reranker=identity, embedding=embedding.model_name, device='cpu',
                documents=9, cases=len(results),
                reranker_passed=sum(r['reranker_top1'] == r['expected'] for r in results),
                pipeline_passed=sum(r['pipeline_top1'] == r['expected'] for r in results),
                fallback='passed', worker_reused=True, cold_rank_seconds=rank_seconds[0],
                warm_rank_max_seconds=max(rank_seconds[1:]), results=results)
            if os.environ.get('RERANKER_TEST_REPORT'):
                Path(os.environ['RERANKER_TEST_REPORT']).write_text(json.dumps(report, indent=2), encoding='utf-8')
            self.assertEqual(report['reranker_passed'], len(results), report)
            self.assertEqual(report['pipeline_passed'], len(results), report)
