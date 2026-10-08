import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from app.rag.reranker import LocalReranker


class RerankerTests(unittest.TestCase):
    def ranker(self, tokenizer, predict):
        ranker = LocalReranker('unused-test-assets', 1)
        self.addCleanup(ranker.close)
        ranker._model = SimpleNamespace(tokenizer=tokenizer, predict=predict)
        return ranker

    def test_fitting_passages_are_not_repeatedly_truncated_or_tokenized(self):
        tokenizer = Mock()
        tokenizer.encode.side_effect = lambda query, passage=None, **kwargs: [0] * (len(query) + len(passage or '') + 3)
        predict = Mock(return_value=[.8, .5])
        ranker = self.ranker(tokenizer, predict)
        self.assertEqual(ranker.rank('query', ['passage one', 'passage two']), [.8, .5])
        self.assertEqual(tokenizer.encode.call_count, 3)
        self.assertEqual(predict.call_args.args[0], [['query', 'passage one'], ['query', 'passage two']])

    def test_long_passages_still_obey_exact_pair_budget(self):
        tokenizer = SimpleNamespace(encode=lambda query, passage=None, **kwargs: [0] * (len(query) + len(passage or '') + 3))
        predict = Mock(return_value=[1.])
        ranker = self.ranker(tokenizer, predict)
        self.assertEqual(ranker.rank('query', ['a' * 1000]), [1.])
        pair = predict.call_args.args[0][0]
        self.assertEqual(len(tokenizer.encode(*pair)), 512)

    def test_invalid_or_missing_scores_fall_back(self):
        tokenizer = SimpleNamespace(encode=lambda *args, **kwargs: [0])
        for scores in ([float('nan')], [float('inf')], []):
            with self.subTest(scores=scores):
                self.assertIsNone(self.ranker(tokenizer, Mock(return_value=scores)).rank('query', ['passage']))

    def test_empty_and_closed_requests_do_not_submit_model_work(self):
        ranker = self.ranker(Mock(), Mock())
        self.assertEqual(ranker.rank('query', []), [])
        ranker.close()
        self.assertIsNone(ranker.rank('query', ['passage']))
