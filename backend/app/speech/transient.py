"""Transient audio is never uploaded externally; only bounded replay receipts persist."""
import hashlib
from datetime import timedelta
from sqlalchemy import select,update
from uuid import uuid4
from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from app.files.tables import speech
from app.files.service import now


def transcribe_direct(files, processor, owner, operation, data):
    if not data or len(data)>processor.maximum:
        raise AppError('SPEECH_SIZE','Recording is empty or exceeds the upload limit.',413)
    digest, token = hashlib.sha256(data).hexdigest(), str(uuid4())
    with files.sessions.begin() as session:
        lock_owner(session,owner)
        row = session.execute(select(speech).where(speech.c.id==operation)).mappings().first()
        if row:
            if row['learner_id'] != owner or row['request_hash'] != digest:
                raise AppError('SPEECH_OPERATION_CONFLICT','Use a new request ID for a different recording.',409)
            if row['expires_at']<=now():
                raise AppError('SPEECH_OPERATION_EXPIRED','Record again to continue.',409)
            if row['result'] is not None: return row['result']
            if row['lease_until'] and row['lease_until']>now():
                raise AppError('SPEECH_BUSY','This recording is still processing. Retry shortly.',429)
            session.execute(update(speech).where(speech.c.id==operation).values(lease_token=token,
                lease_until=now()+timedelta(seconds=processor.timeout+30)))
        else:
            session.execute(speech.insert().values(id=operation,learner_id=owner,request_hash=digest,
                expires_at=now()+timedelta(hours=24),lease_token=token,
                lease_until=now()+timedelta(seconds=processor.timeout+30)))
    try:
        result = processor.transcribe(data,None)
        if hasattr(result,'model_dump'): result=result.model_dump()
        with files.sessions.begin() as session:
            changed=session.execute(update(speech).where(speech.c.id==operation,speech.c.lease_token==token)
                .values(result=result,lease_token=None,lease_until=None))
            if changed.rowcount != 1:
                raise AppError('SPEECH_BUSY','This transcription changed. Retry shortly.',409)
        return result
    except Exception:
        with files.sessions.begin() as session:
            session.execute(update(speech).where(speech.c.id==operation,speech.c.lease_token==token)
                .values(lease_token=None,lease_until=None))
        raise
