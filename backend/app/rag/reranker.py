"""Optional local-only cross-encoder; one bounded task, safe timeout fallback."""
import json
import logging
import math
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, TimeoutError


class LocalReranker:
    def __init__(self, path, timeout):
        self.path, self.timeout = Path(path), timeout
        self._model = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='rag-reranker')
        self._future = None
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
        with self._lock:
            if self._closed:
                return None
            if not passages:
                return []
            if self._future is not None and not self._future.done():
                return None
            self._future = self._executor.submit(self._rank, query, passages)
            future = self._future
        try:
            return future.result(timeout=self.timeout)
        except (TimeoutError, ValueError, OSError, RuntimeError, ImportError):
            return None
        except Exception:
            logging.getLogger('mentra').exception('Optional RAG reranker failed.')
            return None

    def close(self):
        with self._lock:
            self._closed = True
            self._executor.shutdown(wait=False, cancel_futures=True)
