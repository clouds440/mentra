"""Regression fixtures from the preserved 2026-11-02 audit."""
import importlib.util
from pathlib import Path
import unittest
from app.core.config import Settings
from app.rag.worker import IngestionWorker
from types import SimpleNamespace
from unittest.mock import Mock
from app.rag.service import RAGService

path = Path(__file__).resolve().parents[3] / 'docs/library/verification/embedding-audit-2026-11-02-probes.py'
spec = importlib.util.spec_from_file_location('audit_selection_fixtures', path)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class SelectionRegressionTests(unittest.TestCase):
    def test_support_gate_requires_enabled_pinned_reranker(self):
        with self.assertRaisesRegex(ValueError,'requires an enabled reranker'):
            Settings(_env_file=None,rag_min_reranker_score=.5,rag_reranker_path='',rag_reranker_model_revision='')
    def test_source_fetch_survives_usage_failure_after_policy_check(self):
        service = object.__new__(RAGService)
        service.repository = SimpleNamespace(source=Mock(return_value=({}, {'file_id': 'file'})),
            record_usage=Mock(side_effect=RuntimeError('usage unavailable')))
        service.files = SimpleNamespace(binding=Mock(return_value='binding'))
        service._source_policy = Mock()
        self.assertEqual(service.source('owner', 'document', 'version'), ('file', 'binding'))
        service._source_policy.assert_called_once()

    def test_lease_must_cover_embedding_restart(self):
        with self.assertRaisesRegex(ValueError, 'embedding initialization'):
            Settings(_env_file=None, rag_job_lease_seconds=30, rag_parser_timeout=1)

    def test_point_verification_renews_between_bounded_batches(self):
        vector = SimpleNamespace(indexed_chunk_ids=Mock(side_effect=lambda owner, generation, ids: set(ids)))
        repository = SimpleNamespace(stage=Mock())
        worker = IngestionWorker(SimpleNamespace(repository=repository, vector_store=vector,
            settings=SimpleNamespace(rag_job_lease_seconds=300)))
        job = dict(id='job', learner_id='owner', generation_id='generation', attempts=1)
        ids = [str(i) for i in range(1001)]
        self.assertEqual(worker.indexed_ids(job, ids), set(ids))
        self.assertEqual(repository.stage.call_count, 3)
        self.assertEqual([len(call.args[2]) for call in vector.indexed_chunk_ids.call_args_list], [500, 500, 1])

    def test_reranking_retains_diverse_viable_candidates(self):
        for kind in ('diversity', 'duplicates', 'budget'):
            with self.subTest(kind=kind):
                baseline = fixtures.search_case(kind, False)
                actual = fixtures.search_case(kind, True)
                self.assertEqual(actual['count'], baseline['count'])
                self.assertEqual(actual['documents'], baseline['documents'])

    def test_usage_write_failure_does_not_discard_results(self):
        for rerank in (False, True):
            result = fixtures.search_case('usage_failure', rerank)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['count'], 8)
