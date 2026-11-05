"""Transient audio inference runs outside durable replay receipt transactions."""
import hashlib
from app.core.exceptions import AppError
from app.files.speech_receipts import SpeechReceipts

def transcribe_direct(files, processor, owner, operation, data):
    if not data or len(data) > processor.maximum:
        raise AppError('SPEECH_SIZE', 'Recording is empty or exceeds the upload limit.', 413)
    receipts = SpeechReceipts(files.sessions)
    token, previous = receipts.claim(owner, operation, hashlib.sha256(data).hexdigest(), processor.timeout)
    if previous is not None:
        return previous
    try:
        result = processor.transcribe(data, None)
        if hasattr(result, 'model_dump'):
            result = result.model_dump()
        receipts.finish(operation, token, result)
        return result
    except Exception:
        receipts.release(operation, token)
        raise
