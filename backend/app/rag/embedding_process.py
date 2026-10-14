"""Reusable local embedding process with hard, restartable native deadlines."""
import multiprocessing as mp
from pathlib import Path
from threading import Lock
from app.rag.embeddings import EmbeddingModelError, EMBEDDING_CACHE_DIR


def _embedding_worker(connection, config):
    from app.core.config import Settings
    from app.rag.embeddings import SentenceTransformerEmbeddingService
    try:
        settings = Settings(_env_file=None, embedding_model=config['model'], embedding_device=config['device'])
        engine = SentenceTransformerEmbeddingService(settings, model_path=Path(config['path']))
        connection.send(('ok', dict(model_name=engine.model_name, model_version=engine.model_version,
            dimension=engine.dimension, max_tokens=engine.max_tokens)))
        while True:
            message = connection.recv()
            if message is None:
                break
            operation, argument = message
            if operation not in ('token_count', 'query_token_count', 'embed_query', 'embed_documents'):
                connection.send(('error', None))
                continue
            try:
                connection.send(('ok', getattr(engine, operation)(argument)))
            except Exception:
                connection.send(('error', None))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        try:
            connection.send(('error', None))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        connection.close()


class ProcessEmbeddingService:
    def __init__(self, settings, model_path=EMBEDDING_CACHE_DIR, *, worker_target=_embedding_worker):
        self.config = dict(model=settings.embedding_model, device=settings.embedding_device, path=str(model_path))
        self.timeout = settings.embedding_worker_timeout
        self.wait = settings.rag_inference_wait_seconds
        self.initialization_timeout = settings.embedding_initialization_timeout
        self._target = worker_target
        self._lock = Lock()
        self._process = self._connection = None
        self._closed = False
        self._identity = None
        with self._lock:
            self._start()

    def _start(self):
        self._stop()
        context = mp.get_context('spawn')
        self._connection, child = context.Pipe()
        self._process = context.Process(target=self._target, args=(child, self.config), daemon=True)
        self._process.start()
        child.close()
        try:
            if not self._connection.poll(self.initialization_timeout):
                raise EmbeddingModelError('Embedding initialization timed out.')
            status, identity = self._connection.recv()
            if status != 'ok' or not isinstance(identity, dict) or identity.get('model_name') != self.config['model']:
                raise EmbeddingModelError('Embedding initialization failed.')
            if self._identity is not None and self._identity != identity:
                raise EmbeddingModelError('Embedding identity changed; rebuild or reindex the service.')
            self._identity = identity
        except BaseException:
            self._stop()
            raise

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

    def _request(self, operation, argument):
        if not self._lock.acquire(timeout=self.wait):
            raise EmbeddingModelError('Embedding capacity is busy.')
        try:
            if self._closed:
                raise EmbeddingModelError('Embedding worker is closed.')
            if self._process is None or not self._process.is_alive():
                self._start()
            self._connection.send((operation, argument))
            if not self._connection.poll(self.timeout):
                self._stop()
                raise EmbeddingModelError('Embedding inference timed out.')
            status, value = self._connection.recv()
            if status != 'ok':
                raise EmbeddingModelError('Embedding input or inference was unavailable.')
            return value
        except (EOFError, BrokenPipeError, OSError) as error:
            self._stop()
            raise EmbeddingModelError('Embedding worker is unavailable.') from error
        finally:
            self._lock.release()

    @property
    def model_name(self):
        return self._identity['model_name']

    @property
    def model_version(self):
        return self._identity['model_version']

    @property
    def dimension(self):
        return self._identity['dimension']

    @property
    def max_tokens(self):
        return self._identity['max_tokens']

    def token_count(self, text):
        return self._request('token_count', text)

    def query_token_count(self, text):
        return self._request('query_token_count', text)

    def embed_query(self, text):
        return self._request('embed_query', text)

    def embed_documents(self, texts):
        result = []
        for start in range(0, len(texts), 32):
            result.extend(self._request('embed_documents', texts[start:start + 32]))
        return result

    def close(self):
        with self._lock:
            self._closed = True
            self._stop(graceful=True)
