"""Transient recording replay persistence, separate from speech inference."""
from datetime import timedelta
from sqlalchemy import select, update
from uuid import uuid4
from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from .tables import speech
from .service import now


class SpeechReceipts:
    def __init__(self, sessions):
        self.sessions = sessions

    def claim(self, owner, operation, digest, timeout):
        token = str(uuid4())
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            row = session.execute(select(speech).where(speech.c.id == operation)).mappings().first()
            if row:
                if row['learner_id'] != owner or row['request_hash'] != digest:
                    raise AppError('SPEECH_OPERATION_CONFLICT', 'Use a new request ID for a different recording.', 409)
                if row['expires_at'] <= now():
                    raise AppError('SPEECH_OPERATION_EXPIRED', 'Record again to continue.', 409)
                if row['result'] is not None:
                    return None, row['result']
                if row['lease_until'] and row['lease_until'] > now():
                    raise AppError('SPEECH_BUSY', 'This recording is still processing. Retry shortly.', 429)
                session.execute(update(speech).where(speech.c.id == operation).values(
                    lease_token=token, lease_until=now() + timedelta(seconds=timeout + 30)))
            else:
                session.execute(speech.insert().values(id=operation, learner_id=owner, request_hash=digest,
                    expires_at=now() + timedelta(hours=24), lease_token=token,
                    lease_until=now() + timedelta(seconds=timeout + 30)))
        return token, None

    def finish(self, operation, token, result):
        with self.sessions.begin() as session:
            changed = session.execute(update(speech).where(speech.c.id == operation, speech.c.lease_token == token)
                .values(result=result, lease_token=None, lease_until=None))
            if changed.rowcount != 1:
                raise AppError('SPEECH_BUSY', 'This transcription changed. Retry shortly.', 409)

    def release(self, operation, token):
        with self.sessions.begin() as session:
            session.execute(update(speech).where(speech.c.id == operation, speech.c.lease_token == token)
                .values(lease_token=None, lease_until=None))
