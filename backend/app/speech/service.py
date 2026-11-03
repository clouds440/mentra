"""One reusable CPU worker per API process. Hard deadlines can stop native inference."""
import multiprocessing as mp
import threading
from time import monotonic

from app.core.exceptions import AppError
from app.speech.engine import FasterWhisperEngine


def _worker(connection, config):
    engine = FasterWhisperEngine(config)
    try:
        while True:
            message = connection.recv()
            if message is None:
                break
            data, language = message
            message = None
            try:
                result = engine.transcribe(data, language) if data is not None else engine.warm()
                connection.send(('ok', result, engine._runtime.choice.device if engine._runtime else None))
            except AppError as exc:
                connection.send(('error', (exc.code, exc.message, exc.status_code)))
            except Exception:
                # Never send native errors containing audio, paths, or model content to clients/logs.
                connection.send(('error', ('SPEECH_UNAVAILABLE', 'Voice input is unavailable. Please try again later.', 503)))
            finally:
                data = None
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


class SpeechService:
    def __init__(self, settings, worker_target=_worker):
        self.config = dict(model=settings.speech_model, model_path=settings.speech_model_path,
                           device=settings.local_inference_device,
                           threads=settings.speech_cpu_threads, beam_size=settings.speech_beam_size,
                           max_seconds=settings.speech_max_seconds)
        self.timeout = settings.speech_timeout_seconds
        self.maximum = settings.speech_max_upload_bytes
        self._target = worker_target
        self._lock = threading.Lock()
        self._process = self._connection = None
        self._closed = False
        self._device = None

    def _stop(self, graceful=False):
        if self._process is not None:
            # Graceful EOF permits native runtimes to release their resources,
            # but submission/EOF itself must be bounded for a nonreading child.
            if graceful and self._process.is_alive():
                from app.rag.process_ipc import exchange
                try:
                    exchange(self._connection,None,.5,self._process.terminate)
                except (EOFError,BrokenPipeError,OSError,TimeoutError):
                    pass
                self._process.join(timeout=.5)
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

    def _request(self, data, language):
        deadline = monotonic() + self.timeout
        if not self._lock.acquire(blocking=False):
            raise AppError('SPEECH_BUSY', 'Voice input is busy. Please retry shortly.', 429)
        try:
            if self._closed:
                raise AppError('SPEECH_UNAVAILABLE', 'Voice input is unavailable.', 503)
            from app.rag.process_ipc import exchange
            from app.core.inference_device import retry_worker_on_cpu
            for attempt in range(2):
                try:
                    if self._process is None or not self._process.is_alive():
                        self._stop()
                        context = mp.get_context('spawn')
                        self._connection, child = context.Pipe()
                        self._process = context.Process(target=self._target, args=(child, self.config), daemon=True)
                        self._process.start()
                        child.close()
                    reply = exchange(self._connection, (data, language), deadline-monotonic(), self._stop)
                    status,result=reply[:2]
                    if len(reply)>2:
                        self._device=reply[2]
                        if self._device=='cpu': self.config['device']='cpu'
                    if status == 'error': raise AppError(*result)
                    return result
                except TimeoutError:
                    raise AppError('SPEECH_TIMEOUT', 'Transcription took too long. Try a shorter recording.', 504) from None
                except (EOFError,BrokenPipeError,OSError):
                    self._stop()
                    if retry_worker_on_cpu(self.config['device'],self._device,deadline-monotonic(),attempt):
                        self.config['device']=self._device='cpu'
                        continue
                    raise AppError('SPEECH_UNAVAILABLE', 'Voice input is unavailable. Please retry.', 503) from None
        finally:
            self._lock.release()

    def transcribe(self, data: bytes, language: str | None):
        if not data or len(data) > self.maximum:
            raise AppError('SPEECH_SIZE', 'Recording is empty or exceeds the upload limit.', 413)
        return self._request(data, language)

    def warm(self):
        return self._request(None, None)

    def close(self):
        with self._lock:
            self._closed = True
            self._stop(graceful=True)
