"""Optional local-only cross-encoder; one bounded task, safe timeout fallback."""
import json
import math
from pathlib import Path
from threading import Lock, local
import multiprocessing as mp
import time


from app.core.logging import workflow_logger


def _rerank_worker(connection, path):
    engine = LocalReranker(path, 5)
    try:
        while True:
            message = connection.recv()
            if message is None:
                break
            try:
                scores = engine._rank(*message)
                connection.send({'scores': scores, 'truncated_passages': engine.truncated_passages,
                    'winning_spans': engine.winning_spans, 'window_pairs': engine.window_pairs})
            except Exception as error:
                reason = ('query_budget' if 'Query exceeds' in str(error) else
                          'pair_budget' if 'window coverage' in str(error) else
                          'invalid_scores' if 'invalid scores' in str(error) else 'inference_error')
                connection.send({'error': reason})
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()

@workflow_logger.connect_module(default_outcome='success')
class LocalReranker:
    def __init__(self, path, timeout, *, worker_target=_rerank_worker, cooldown_seconds=5, cold_timeout=30, expected_revision=''):
        self.path, self.timeout = Path(path), timeout
        self._model = None
        self._process = self._connection = None
        self._target = worker_target
        self._lock = Lock()
        self._closed = False
        self._request_state = local()
        self.cooldown_seconds, self.cold_timeout = cooldown_seconds, cold_timeout
        self._retry_after = 0
        self.last_reason = None
        self.expected_revision = expected_revision
        self.truncated_passages = 0
        self.winning_spans = []
        self.window_pairs = 0

    # Projection happens after the inference lock is released. A different caller
    # must not overwrite this caller's score provenance or fallback reason.
    @property
    def last_reason(self): return getattr(self._request_state,'reason',None)
    @last_reason.setter
    def last_reason(self,value): self._request_state.reason=value
    @property
    def winning_spans(self): return getattr(self._request_state,'spans',[])
    @winning_spans.setter
    def winning_spans(self,value): self._request_state.spans=value
    @property
    def window_pairs(self): return getattr(self._request_state,'pairs',0)
    @window_pairs.setter
    def window_pairs(self,value): self._request_state.pairs=value
    @property
    def truncated_passages(self): return getattr(self._request_state,'truncated',0)
    @truncated_passages.setter
    def truncated_passages(self,value): self._request_state.truncated=value

    def _rank(self, query, passages):
        self.truncated_passages = 0
        if self._model is None:
            metadata = json.loads((self.path / 'model-metadata.json').read_text(encoding='utf-8'))
            if not metadata.get('model_name') or not metadata.get('model_version'):
                raise ValueError('Reranker metadata is missing its resolved identity.')
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(str(self.path), device='cpu', local_files_only=True,
                                       trust_remote_code=False, max_length=512)
        tokenizer = self._model.tokenizer
        if len(tokenizer.encode(query, truncation=False)) > 240:
            raise ValueError('Query exceeds reranker pair budget.')
        pairs = []
        owners = []
        spans = []
        from app.rag.text_windows import token_windows
        for index, passage in enumerate(passages):
            if len(tokenizer.encode(query, passage, truncation=False)) <= 512:
                pairs.append([query, passage])
                owners.append(index)
                spans.append([0,len(passage)])
                continue
            windows = token_windows(passage,
                lambda part: len(tokenizer.encode(query, part, truncation=False)), 512, max_windows=4)
            pairs.extend([query, window] for window in windows)
            owners.extend([index] * len(windows))
            start=0
            for window in windows:
                spans.append([start,start+len(window)])
                start+=len(window)
        self.window_pairs=len(pairs)
        scores = [float(s) for s in self._model.predict(pairs, batch_size=8)]
        if len(scores) != len(pairs) or any(not math.isfinite(score) for score in scores):
            raise ValueError('Reranker returned invalid scores.')
        merged = [float('-inf')] * len(passages)
        self.winning_spans=[None]*len(passages)
        for owner, score, span in zip(owners, scores, spans, strict=True):
            if score>merged[owner]:
                merged[owner]=score
                self.winning_spans[owner]=span
        return merged

    def rank(self, query, passages):
        if not self._lock.acquire(blocking=False):
            self.last_reason = 'busy'
            return None
        try:
            started = time.monotonic()
            self.last_reason = None
            self.truncated_passages = 0
            self.winning_spans = []
            self.window_pairs = 0
            if self._closed:
                self.last_reason = 'closed'
                return None
            if not passages:
                return []
            if time.monotonic() < self._retry_after:
                self.last_reason = 'cooldown'
                return None
            cold = self._process is None or not self._process.is_alive()
            if cold:
                if self._target is _rerank_worker:
                    try:
                        from model_assets import verify_manifest
                        verify_manifest(self.path, role='reranker')
                        metadata = json.loads((self.path / 'model-metadata.json').read_text(encoding='utf-8'))
                        if not metadata.get('model_name') or not metadata.get('model_version'):
                            raise ValueError('Missing identity')
                        if self.expected_revision and metadata['model_version'] != self.expected_revision:
                            raise ValueError('Revision mismatch')
                    except (OSError, ValueError):
                        self.last_reason = 'missing_or_invalid_assets'
                        self._retry_after = time.monotonic() + self.cooldown_seconds
                        return None
                self._stop()
                context = mp.get_context('spawn')
                self._connection, child = context.Pipe()
                self._process = context.Process(target=self._target, args=(child, str(self.path)), daemon=True)
                self._process.start()
                child.close()
            from app.rag.process_ipc import exchange
            try:
                scores = exchange(self._connection,(query,passages),
                    (self.cold_timeout if cold else self.timeout)-(time.monotonic()-started),self._stop)
            except TimeoutError:
                self.last_reason = 'cold_timeout' if cold else 'inference_timeout'
                self._retry_after = time.monotonic() + self.cooldown_seconds
                workflow_logger.set_outcome('degraded', code='RERANKER_UNAVAILABLE')
                return None
            if isinstance(scores, dict):
                if 'error' in scores:
                    self.last_reason = scores['error']
                    if self.last_reason not in ('query_budget','pair_budget'):
                        self._stop()
                        self._retry_after = time.monotonic() + self.cooldown_seconds
                    return None
                self.truncated_passages = scores.get('truncated_passages', 0)
                self.winning_spans = scores.get('winning_spans', [])
                self.window_pairs = scores.get('window_pairs', 0)
                scores = scores.get('scores')
            if scores is None or len(scores) != len(passages) or any(not math.isfinite(s) for s in scores):
                self.last_reason = 'invalid_scores'
                self._stop()
                self._retry_after = time.monotonic() + self.cooldown_seconds
                return None
            return scores
        except Exception:
            self._stop()
            self.last_reason = 'worker_unavailable'
            self._retry_after = time.monotonic() + self.cooldown_seconds
            workflow_logger.set_outcome('degraded', code='RERANKER_UNAVAILABLE')
            return None
        finally:
            self._lock.release()

    def warmup(self):
        """Bounded optional local warmup; failure leaves retrieval fallback intact."""
        return self.rank('local model readiness', ['local inference readiness']) is not None

    def _stop(self, graceful=False):
        if self._process is not None:
            if graceful and self._process.is_alive():
                try:
                    self._connection.send(None)
                    self._process.join(timeout=2)
                except (EOFError, BrokenPipeError, OSError):
                    pass
            if self._process.is_alive():
                self._process.terminate()
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=2)
            self._process.close()
        if self._connection is not None:
            self._connection.close()
        self._process = self._connection = None

    def close(self):
        with self._lock:
            self._closed = True
            self._stop(graceful=True)
