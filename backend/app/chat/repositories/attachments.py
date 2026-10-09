from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, func
from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from .tables import attachments, conversations


class AttachmentRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def create(self, owner, filename, data):
        now = datetime.now(timezone.utc)
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            session.execute(delete(attachments).where(attachments.c.learner_id == owner,
                attachments.c.conversation_id.is_(None), attachments.c.created_at < now - timedelta(days=1)))
            size = session.execute(select(func.coalesce(func.sum(attachments.c.size_bytes), 0)).where(attachments.c.learner_id == owner)).scalar_one()
            if size + len(data) > 100 * 1024 * 1024:
                raise AppError('CHAT_ATTACHMENT_CAPACITY', 'Chat file storage is full. Remove files or their conversations before uploading more.', 409)
            identifier = str(uuid4())
            session.execute(attachments.insert().values(id=identifier, learner_id=owner, filename=filename,
                data=data, size_bytes=len(data), created_at=now))
            return dict(id=identifier, filename=filename, size_bytes=len(data))

    @staticmethod
    def bind(session, owner, identifiers, conversation_id):
        if not identifiers:
            return []
        rows = session.execute(select(attachments).where(attachments.c.learner_id == owner,
            attachments.c.id.in_(identifiers))).mappings().all()
        if len(rows) != len(set(identifiers)) or any(row['conversation_id'] not in (None, conversation_id) for row in rows):
            raise AppError('CHAT_ATTACHMENT_NOT_FOUND', 'An attachment is unavailable for this conversation.', 404)
        if any(row['conversation_id'] is None and row['created_at'] < datetime.now(timezone.utc) - timedelta(days=1) for row in rows):
            raise AppError('CHAT_ATTACHMENT_EXPIRED', 'Upload this file again before sending.', 409)
        session.execute(update(attachments).where(attachments.c.learner_id == owner,
            attachments.c.id.in_(identifiers)).values(conversation_id=conversation_id))
        return [dict(id=row['id'], filename=row['filename'], size_bytes=row['size_bytes']) for row in rows]

    def read(self, owner, identifier, conversation_id):
        with self.sessions() as session:
            row = session.execute(select(attachments).join(conversations, attachments.c.conversation_id == conversations.c.id).where(
                attachments.c.id == identifier, attachments.c.learner_id == owner,
                attachments.c.conversation_id == conversation_id, conversations.c.deleted_at.is_(None))).mappings().first()
            if not row:
                raise AppError('CHAT_ATTACHMENT_NOT_FOUND', 'This file is no longer available.', 404)
            return dict(row)

    def save_extraction(self, owner, identifier, conversation_id, extraction):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            result = session.execute(update(attachments).where(attachments.c.id == identifier,
                attachments.c.learner_id == owner, attachments.c.conversation_id == conversation_id).values(extraction=extraction, extraction_error=None))
            if not result.rowcount:
                raise AppError('CHAT_ATTACHMENT_NOT_FOUND', 'This file is no longer available.', 404)

    def extraction_failed(self, owner, identifier, error):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            session.execute(update(attachments).where(attachments.c.id == identifier, attachments.c.learner_id == owner)
                .values(extraction_error=error[:500]))

    def link_library(self, owner, identifier, result):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            session.execute(update(attachments).where(attachments.c.id == identifier, attachments.c.learner_id == owner)
                .values(library_result=result))

    def detail(self, owner, identifier, conversation_id):
        row = self.read(owner, identifier, conversation_id)
        return dict(id=row['id'], filename=row['filename'], size_bytes=row['size_bytes'],
            ready=row['extraction'] is not None, error=row['extraction_error'],
            warnings=row['extraction']['warnings'] if row['extraction'] else [], library_result=row['library_result'])

    def remove(self, owner, identifier):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            # Only unsent uploads can be removed independently of their transcript.
            session.execute(delete(attachments).where(attachments.c.id == identifier,
                attachments.c.learner_id == owner, attachments.c.conversation_id.is_(None)))
