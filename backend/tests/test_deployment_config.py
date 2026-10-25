from pathlib import Path
import unittest
import yaml


class DeploymentConfigTests(unittest.TestCase):
    def test_reranker_cpu_budget_reaches_api_and_assessment_worker(self):
        from app.core.config import Settings
        from pydantic import ValidationError
        root = Path(__file__).resolve().parents[2]
        config = yaml.safe_load((root / 'docker-compose.yml').read_text())
        key = 'RAG_RERANKER_MAX_CANDIDATES'
        for role in ('backend', 'assessment-worker'):
            self.assertEqual(config['services'][role]['environment'][key], '${RAG_RERANKER_MAX_CANDIDATES:-20}')
        self.assertEqual(Settings(_env_file=None).rag_reranker_max_candidates, 20)
        for invalid in (0, 41):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, rag_reranker_max_candidates=invalid)

    def test_api_and_grading_worker_share_model_environment(self):
        root = Path(__file__).resolve().parents[2]
        config = yaml.safe_load((root / 'docker-compose.yml').read_text())
        api = config['services']['backend']['environment']
        worker = config['services']['assessment-worker']['environment']
        for key, value in config['x-model-settings'].items():
            self.assertEqual(api[key], value, key)
            self.assertEqual(worker[key], value, key)
        for role in ('backend', 'rag-worker', 'events-worker', 'assessment-worker', 'summarizer', 'files-worker'):
            budget = config['x-database-budget'] if role == 'backend' else config['x-worker-database-budget']
            for key, value in budget.items():
                self.assertEqual(config['services'][role]['environment'][key], value)
        summary = config['services']['summarizer']['environment']
        for key, value in config['x-model-settings'].items():
            self.assertEqual(summary[key], value, key)
