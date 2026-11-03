"""Legacy stored-audio intake validates native codecs in a killable child."""
import multiprocessing as mp
from app.core.exceptions import AppError
from app.rag.process_ipc import exchange


def _validate(connection, seconds):
    try:
        from .engine import decode_audio
        try:
            decode_audio(connection.recv(), seconds)
            connection.send(('ok', None))
        except AppError as error:
            connection.send(('error', (error.code,error.message,error.status_code)))
        except Exception:
            connection.send(('error',('SPEECH_AUDIO_INVALID','This recording could not be read.',422)))
    finally:
        connection.close()


def validate_audio(data, seconds, timeout):
    context = mp.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_validate,args=(child,seconds),daemon=True)
    def stop():
        if process.is_alive(): process.terminate()
        process.join(timeout=1)
        if process.is_alive(): process.kill(); process.join(timeout=1)
        parent.close()
    try:
        process.start(); child.close()
        try:
            status, result = exchange(parent,data,timeout,stop)
        except TimeoutError:
            raise AppError('SPEECH_TIMEOUT','Audio validation took too long.',504) from None
        if status == 'error': raise AppError(*result)
    finally:
        if process.pid is not None: stop(); process.close()
        child.close(); parent.close()
