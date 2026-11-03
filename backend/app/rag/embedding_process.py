"""Reusable local embedding process with hard, restartable native deadlines."""
import multiprocessing as mp
from pathlib import Path
from threading import Lock
from app.rag.embeddings import EmbeddingModelError, EMBEDDING_CACHE_DIR


def _embedding_worker(connection, config):
    from app.core.config import Settings
    from app.rag.embeddings import SentenceTransformerEmbeddingService
    try:
        settings = Settings(_env_file=None, embedding_model=config['model'], embedding_device=config['device'],
                            embedding_model_revision=config.get('revision', ''))
        engine = SentenceTransformerEmbeddingService(settings, model_path=Path(config['path']))
        def respond(status,value):
            connection.send((status,value,engine._runtime.choice.device))
        connection.send(('ok', dict(model_name=engine.model_name, model_version=engine.model_version,
            dimension=engine.dimension, max_tokens=engine.max_tokens,inference_device=engine._runtime.choice.device)))
        while True:
            message = connection.recv()
            if message is None:
                break
            operation, argument = message
            if operation == 'token_counts':
                respond('ok', [engine.token_count(value) for value in argument])
                continue
            if operation == 'chunk_blocks':
                from app.rag.processing import chunk_blocks
                from app.rag.errors import ExtractionError
                try:
                    respond('ok', chunk_blocks(embedding=engine, **argument))
                except ExtractionError as error:
                    respond('extraction_error', str(error))
                except Exception:
                    connection.send(('error', None))
                continue
            if operation not in ('token_count', 'query_token_count', 'embed_query', 'embed_documents', 'embed_similarity'):
                connection.send(('error', None))
                continue
            try:
                respond('ok', getattr(engine, operation)(argument))
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
        if self.config['device'] == 'auto':
            self.config['device'] = settings.local_inference_device
        self.config['revision'] = settings.embedding_model_revision
        self.timeout = settings.embedding_worker_timeout
        self.wait = settings.rag_inference_wait_seconds
        self.initialization_timeout = settings.embedding_initialization_timeout
        self._target = worker_target
        self._lock = Lock()
        self._process = self._connection = None
        self._closed = False
        self._identity = None
        self._device = None
        with self._lock:
            self._start()

    def prepare(self):
        """Bounded readiness check before the caller starts its query budget."""
        if not self._lock.acquire(timeout=self.wait):
            raise EmbeddingModelError('Embedding capacity is busy.')
        try:
            if self._closed:
                raise EmbeddingModelError('Embedding worker is closed.')
            if self._process is None or not self._process.is_alive():
                self._start()
        finally:
            self._lock.release()

    def _start(self, timeout=None):
        from time import monotonic
        started=monotonic()
        budget=self.initialization_timeout if timeout is None else max(0,min(timeout,self.initialization_timeout))
        self._stop()
        context = mp.get_context('spawn')
        self._connection, child = context.Pipe()
        self._process = context.Process(target=self._target, args=(child, self.config), daemon=True)
        self._process.start()
        child.close()
        try:
            if not self._connection.poll(budget):
                raise EmbeddingModelError('Embedding initialization timed out.')
            status, identity = self._connection.recv()
            if status != 'ok' or not isinstance(identity, dict) or identity.get('model_name') != self.config['model']:
                raise EmbeddingModelError('Embedding initialization failed.')
            self._device=identity.pop('inference_device',None)
            if self._device=='cpu': self.config['device']='cpu'
            if self._identity is not None and self._identity != identity:
                raise EmbeddingModelError('Embedding identity changed; rebuild or reindex the service.')
            self._identity = identity
        except (EOFError,BrokenPipeError,OSError):
            self._stop()
            from app.core.inference_device import retry_worker_on_cpu
            remaining=budget-(monotonic()-started)
            if retry_worker_on_cpu(self.config['device'],self._device,remaining,0):
                self.config['device']=self._device='cpu'
                return self._start(timeout=remaining)
            raise
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

    def _request(self, operation, argument, *, timeout=None):
        if not self._lock.acquire(timeout=self.wait):
            raise EmbeddingModelError('Embedding capacity is busy.')
        try:
            if self._closed:
                raise EmbeddingModelError('Embedding worker is closed.')
            from app.rag.process_ipc import exchange
            from app.core.inference_device import retry_worker_on_cpu
            from time import monotonic
            # Cold startup has its separately admitted initialization budget.
            # CPU recovery during an existing operation shares that operation's
            # remaining deadline; it must not open another full startup window.
            if self._process is None or not self._process.is_alive(): self._start()
            deadline=monotonic()+(timeout or self.timeout)
            for attempt in range(2):
                try:
                    if self._process is None or not self._process.is_alive(): self._start(timeout=deadline-monotonic())
                    try:
                        reply=exchange(self._connection,(operation,argument),deadline-monotonic(),self._stop)
                        status,value=reply[:2]
                        if len(reply)>2:
                            self._device=reply[2]
                            if self._device=='cpu': self.config['device']='cpu'
                    except TimeoutError as error:
                        raise EmbeddingModelError('Embedding inference timed out.') from error
                    if status == 'extraction_error':
                        from app.rag.errors import ExtractionError
                        raise ExtractionError(value)
                    if status != 'ok': raise EmbeddingModelError('Embedding input or inference was unavailable.')
                    return value
                except (EOFError,BrokenPipeError,OSError):
                    self._stop()
                    if retry_worker_on_cpu(self.config['device'],self._device,deadline-monotonic(),attempt):
                        self.config['device']=self._device='cpu'
                        continue
                    raise
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

    def chunk_blocks(self, blocks, owner, document_id, generation_id, max_chunks, max_seconds, *, target_tokens=450):
        return self._request('chunk_blocks', dict(blocks=blocks, owner=owner,
            document_id=document_id, generation_id=generation_id, max_chunks=max_chunks,
            max_seconds=max_seconds, target_tokens=target_tokens), timeout=max_seconds + 1)

    def query_token_count(self, text):
        return self._request('query_token_count', text)

    def embed_query(self, text):
        return self._request('embed_query', text)

    def _embed_batches(self, operation, texts):
        result = []
        for start in range(0, len(texts), 32):
            values = texts[start:start + 32]
            counts = self._request('token_counts', values)
            batch, used = [], 0
            for value, count in zip(values, counts, strict=True):
                if batch and used + count > 4096:
                    result.extend(self._request(operation, batch))
                    batch, used = [], 0
                batch.append(value)
                used += count
            if batch:
                result.extend(self._request(operation, batch))
        return result

    def embed_documents(self, texts):
        return self._embed_batches('embed_documents', texts)

    def embed_similarity(self, texts):
        return self._embed_batches('embed_similarity', texts)

    def close(self):
        with self._lock:
            self._closed = True
            self._stop(graceful=True)
