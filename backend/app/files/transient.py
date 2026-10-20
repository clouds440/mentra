from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select, update
from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from .tables import speech, assets
from .service import now, missing


def transcribe_file(files, processor, owner, file_id):
    token = str(uuid4())
    with files.sessions.begin() as session:
        lock_owner(session, owner)
        row = (
            session.execute(
                select(speech).where(
                    speech.c.id == file_id, speech.c.learner_id == owner
                )
            )
            .mappings()
            .first()
        )
        if row:
            if row["expires_at"] <= now():
                raise missing()
            if row["result"] is not None:
                return row["result"]
            if row["lease_until"] and row["lease_until"] > now():
                raise AppError(
                    "SPEECH_BUSY",
                    "This recording is still processing. Retry shortly.",
                    429,
                )
            session.execute(
                update(speech)
                .where(speech.c.id == file_id)
                .values(lease_token=token, lease_until=now() + timedelta(minutes=2))
            )
        else:
            session.execute(
                speech.insert().values(
                    id=file_id,
                    learner_id=owner,
                    expires_at=now() + timedelta(hours=24),
                    lease_token=token,
                    lease_until=now() + timedelta(minutes=2),
                )
            )
            files.bind(
                session, owner, file_id, "speech", dict(speech_operation_id=file_id)
            )
    try:
        result = processor.transcribe(files.read(owner, file_id), None)
        if hasattr(result, "model_dump"):
            result = result.model_dump()
        with files.sessions.begin() as session:
            changed = session.execute(
                update(speech)
                .where(speech.c.id == file_id, speech.c.lease_token == token)
                .values(result=result, lease_token=None, lease_until=None)
            )
            if not changed.rowcount:
                raise AppError(
                    "SPEECH_BUSY", "This transcription changed. Please retry.", 409
                )
            files.release(session, owner, speech_operation_id=file_id)
            session.execute(
                update(assets).where(assets.c.id == file_id).values(expires_at=now())
            )
        return result
    except Exception as error:
        with files.sessions.begin() as session:
            session.execute(
                update(speech)
                .where(speech.c.id == file_id, speech.c.lease_token == token)
                .values(lease_token=None, lease_until=now())
            )
            if (
                isinstance(error, AppError)
                and error.status_code < 500
                and error.status_code != 429
            ):
                files.release(session, owner, speech_operation_id=file_id)
                session.execute(
                    update(assets)
                    .where(assets.c.id == file_id)
                    .values(expires_at=now())
                )
        raise
