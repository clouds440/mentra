"""Optional local-only cross-encoder; one bounded task, safe timeout fallback."""
import json
import logging
import math
from pathlib import Path
from threading import Lock
import multiprocessing as mp


from app.core.logging import workflow_logger


def _rerank_worker(connection, path):
    engine = LocalReranker(path, 5)
    try:
        while True:
            message = connection.recv()
            if message is None:
                break
            try:
                connection.send(engine._rank(*message))
            except Exception:
                connection.send(None)
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()

@workflow_logger.connect_module(default_outcome='success')
class LocalReranker:
    def __init__(self, path, timeout, *, worker_target=_rerank_worker):
        self.path, self.timeout = Path(path), timeout
        self._model = None
        self._process = self._connection = None
        self._target = worker_target
        self._lock = Lock()
        self._closed = False

    def _rank(self, query, passages):
        if self._model is None:
            metadata = json.loads((self.path / 'model-metadata.json').read_text(encoding='utf-8'))
            if not metadata.get('model_name') or not metadata.get('model_version'):
                raise ValueError('Reranker metadata is missing its resolved identity.')
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(str(self.path), local_files_only=True, trust_remote_code=False, max_length=512)
        tokenizer = self._model.tokenizer
        if len(tokenizer.encode(query, truncation=False)) > 240:
            raise ValueError('Query exceeds reranker pair budget.')
        pairs = []
        for passage in passages:
            if len(tokenizer.encode(query, passage, truncation=False)) <= 512:
                pairs.append([query, passage])
                continue
            low, high = 0, len(passage)
            while low < high:
                mid = (low + high + 1) // 2
                if len(tokenizer.encode(query, passage[:mid], truncation=False)) <= 512:
                    low = mid
                else:
                    high = mid - 1
            pairs.append([query, passage[:low]])
        scores = [float(s) for s in self._model.predict(pairs, batch_size=8)]
        if len(scores) != len(passages) or any(not math.isfinite(score) for score in scores):
            raise ValueError('Reranker returned invalid scores.')
        return scores

    def rank(self, query, passages):
        if not self._lock.acquire(blocking=False):
            return None
        try:
            if self._closed:
                return None
            if not passages:
                return []
            cold = self._process is None or not self._process.is_alive()
            if cold:
                self._stop()
                context = mp.get_context('spawn')
                self._connection, child = context.Pipe()
                self._process = context.Process(target=self._target, args=(child, str(self.path)), daemon=True)
                self._process.start()
                child.close()
            self._connection.send((query, passages))
            # Cold model loading has a separate bounded initialization allowance.
            if not self._connection.poll(max(30, self.timeout) if cold else self.timeout):
                self._stop()
                workflow_logger.set_outcome('degraded', code='RERANKER_UNAVAILABLE')
                return None
            return self._connection.recv()
        except Exception:
            self._stop()
            workflow_logger.set_outcome('degraded', code='RERANKER_UNAVAILABLE')
            return None
        finally:
            self._lock.release()

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
