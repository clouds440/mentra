import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from app.rag.reranker import LocalReranker


class RerankerTests(unittest.TestCase):
    def test_interactive_deadline_caps_cold_start_without_changing_global_budget(self):
        import time
        ranker = LocalReranker('unused', 5, worker_target=nonreading_worker, cold_timeout=30)
        self.addCleanup(ranker.close)
        start = time.monotonic()
        self.assertIsNone(ranker.rank('query', ['passage'], timeout_seconds=.1))
        self.assertLess(time.monotonic()-start, 3)
        self.assertEqual(ranker.cold_timeout, 30)
        self.assertEqual(ranker.last_reason, 'cold_timeout')

    def test_busy_caller_cannot_overwrite_another_threads_diagnostics(self):
        from concurrent.futures import ThreadPoolExecutor
        ranker=LocalReranker('unused',1)
        self.addCleanup(ranker.close)
        ranker.last_reason=None; ranker.winning_spans=[[0,5]]
        ranker._lock.acquire()
        try:
            def busy():
                self.assertIsNone(ranker.rank('query',['passage']))
                ranker.winning_spans=[]
                return ranker.last_reason
            with ThreadPoolExecutor(1) as pool:
                self.assertEqual(pool.submit(busy).result(),'busy')
            self.assertIsNone(ranker.last_reason)
            self.assertEqual(ranker.winning_spans,[[0,5]])
        finally: ranker._lock.release()
    def test_deadline_covers_pipe_submission_to_nonreading_worker(self):
        import time
        ranker=LocalReranker('unused',.1,worker_target=nonreading_worker,cold_timeout=.1)
        self.addCleanup(ranker.close)
        start=time.monotonic()
        self.assertIsNone(ranker.rank('query',['x' * 2_000_000]))
        self.assertLess(time.monotonic()-start,8)
        self.assertEqual(ranker.last_reason,'cold_timeout')
    def test_warmup_reuses_worker_for_first_real_request(self):
        ranker=LocalReranker('unused', 1, worker_target=fake_worker)
        self.addCleanup(ranker.close)
        self.assertTrue(ranker.warmup())
        process=ranker._process
        self.assertEqual(ranker.rank('query', ['passage']), [1.])
        self.assertIs(process, ranker._process)
    def test_revision_mismatch_falls_back_without_loading_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'model-metadata.json').write_text(json.dumps(dict(model_name='test', model_version='v1')))
            ranker = LocalReranker(path, 1, expected_revision='v2')
            self.addCleanup(ranker.close)
            self.assertIsNone(ranker.rank('query', ['passage']))
            self.assertEqual(ranker.last_reason, 'missing_or_invalid_assets')
            self.assertIsNone(ranker._process)

    def test_missing_assets_use_cooldown_without_starting_worker(self):
        ranker = LocalReranker('missing-audit-model-assets', 1)
        self.addCleanup(ranker.close)
        self.assertIsNone(ranker.rank('query', ['passage']))
        self.assertEqual(ranker.last_reason, 'missing_or_invalid_assets')
        self.assertIsNone(ranker._process)
        self.assertIsNone(ranker.rank('query', ['passage']))
        self.assertEqual(ranker.last_reason, 'cooldown')
    def test_model_load_is_cpu_local_only_and_reused_with_plain_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'model-metadata.json').write_text(json.dumps(dict(
                model_name='cross-encoder/mmarco-mMiniLMv2-L12-H384-v1', model_version='resolved-revision')))
            model = SimpleNamespace(tokenizer=SimpleNamespace(encode=lambda *a, **k: [0]),
                                    predict=Mock(return_value=[.9]))
            ranker = LocalReranker(path, 5)
            self.addCleanup(ranker.close)
            with patch('sentence_transformers.CrossEncoder', return_value=model) as loader:
                ranker._rank('plain query', ['plain passage'])
                ranker._rank('plain query', ['plain passage'])
            loader.assert_called_once_with(str(path), device='cpu', local_files_only=True,
                                           trust_remote_code=False, max_length=512)
            model.predict.assert_called_with([['plain query', 'plain passage']], batch_size=8)

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
        self.assertEqual(ranker._rank('query', ['passage one', 'passage two']), [.8, .5])
        self.assertEqual(tokenizer.encode.call_count, 3)
        self.assertEqual(predict.call_args.args[0], [['query', 'passage one'], ['query', 'passage two']])

    def test_long_passages_still_obey_exact_pair_budget(self):
        tokenizer = SimpleNamespace(encode=lambda query, passage=None, **kwargs: [0] * (len(query) + len(passage or '') + 3))
        predict = Mock(side_effect=lambda pairs, **kw: [1.] * len(pairs))
        ranker = self.ranker(tokenizer, predict)
        self.assertEqual(ranker._rank('query', ['a' * 1000]), [1.])
        pair = predict.call_args.args[0][0]
        self.assertEqual(len(tokenizer.encode(*pair)), 512)
        self.assertEqual(ranker.truncated_passages, 0)
        self.assertEqual(''.join(pair[1] for pair in predict.call_args.args[0]), 'a' * 1000)

    def test_late_support_is_scored_and_window_overflow_is_explicit(self):
        tokenizer = SimpleNamespace(encode=lambda query, passage=None, **kwargs: [0] * (len(query) + len(passage or '') + 3))
        predict = Mock(side_effect=lambda pairs, **kw: [2. if 'ANSWER' in p else -2. for _, p in pairs])
        ranker = self.ranker(tokenizer, predict)
        self.assertEqual(ranker._rank('query', ['a' * 600 + ' ANSWER']), [2.])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            ranker._rank('query', ['a' * 3000])

    def test_invalid_or_missing_scores_fall_back(self):
        tokenizer = SimpleNamespace(encode=lambda *args, **kwargs: [0])
        for scores in ([float('nan')], [float('inf')], []):
            with self.subTest(scores=scores):
                with self.assertRaises(ValueError):
                    self.ranker(tokenizer, Mock(return_value=scores))._rank('query', ['passage'])

    def test_empty_and_closed_requests_do_not_submit_model_work(self):
        ranker = self.ranker(Mock(), Mock())
        self.assertEqual(ranker.rank('query', []), [])
        ranker.close()
        self.assertIsNone(ranker.rank('query', ['passage']))

    def test_native_hang_is_killed_and_next_request_restarts(self):
        ranker = LocalReranker('unused', .05, worker_target=fake_worker, cooldown_seconds=0)
        self.addCleanup(ranker.close)
        self.assertEqual(ranker.rank('query', ['passage']), [1.])
        process = ranker._process
        self.assertIsNone(ranker.rank('hang', ['passage']))
        self.assertIsNone(ranker._process)
        self.assertEqual(ranker.rank('query', ['passage']), [1.])
        self.assertIsNot(ranker._process, process)


def fake_worker(connection, path):
    import time
    try:
        while True:
            message = connection.recv()
            if message is None:
                break
            query, passages = message
            if query == 'hang':
                time.sleep(60)
            connection.send([1.] * len(passages))
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


def nonreading_worker(connection, path):
    import time
    time.sleep(60)


class RerankerBakeTests(unittest.TestCase):
    def test_bake_pins_revision_downloads_tokenizer_and_records_identity(self):
        from bake_reranker_model import bake_model
        for weight in ('model.safetensors', 'pytorch_model.bin'):
            with self.subTest(weight=weight), tempfile.TemporaryDirectory() as directory:
                info = SimpleNamespace(sha='resolved-revision', siblings=[SimpleNamespace(rfilename=weight)])
                with patch('bake_reranker_model.model_info', return_value=info), \
                     patch('bake_reranker_model.snapshot_download') as download:
                    bake_model('selected-model', Path(directory))
                args = download.call_args.kwargs
                self.assertEqual(args['revision'], 'resolved-revision')
                self.assertEqual(args['repo_id'], 'selected-model')
                self.assertIn(weight, args['allow_patterns'])
                self.assertIn('*.model', args['allow_patterns'])
                self.assertEqual(json.loads((Path(directory) / 'model-metadata.json').read_text()),
                                 dict(model_name='selected-model', model_version='resolved-revision'))

    def test_bake_rejects_missing_weights(self):
        from bake_reranker_model import bake_model
        with patch('bake_reranker_model.model_info', return_value=SimpleNamespace(sha='v1', siblings=[])), \
             patch('bake_reranker_model.snapshot_download') as download:
            with self.assertRaises(RuntimeError):
                bake_model('unsupported')
            download.assert_not_called()
