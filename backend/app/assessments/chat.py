"""Chat-scoped practice drafts; publishing copies the immutable grading key once."""
from uuid import uuid4
from sqlalchemy import select, update, func
from app.core.exceptions import AppError
from app.chat.repositories.tables import conversations
from .repositories.tables import assessments, chat_drafts, preferences
from app.core.logging import workflow_logger


@workflow_logger.connect_module(default_outcome='success')
class ChatAssessments:
    def __init__(self, repository):
        self.repository = repository

    def _conversation(self, session, owner, conversation):
        if not session.scalar(select(conversations.c.id).where(conversations.c.id == conversation,
                conversations.c.learner_id == owner, conversations.c.deleted_at.is_(None))):
            raise AppError('CHAT_NOT_FOUND', 'Conversation unavailable.', 404)

    def find_saved(self, owner, query):
        with self.repository.sessions() as session:
            statement = select(assessments).where(assessments.c.learner_id == owner)
            if query: statement = statement.where(func.strpos(func.lower(assessments.c.title), query.lower()) > 0)
            rows = session.execute(statement.order_by(assessments.c.created_at.desc()).limit(3)).mappings()
            return [self.repository.public(row) for row in rows]

    def _draft(self, session, owner, identifier):
        row = session.execute(select(chat_drafts).where(chat_drafts.c.learner_id == owner,
            chat_drafts.c.id == identifier)).mappings().first()
        if not row: raise AppError('ASSESSMENT_DRAFT_NOT_FOUND', 'Chat assessment unavailable.', 404)
        self._conversation(session, owner, row['conversation_id'])
        return dict(row)

    def public(self, row):
        return dict(id=row['id'], conversation_id=row['conversation_id'], assessment_id=row['assessment_id'],
                    assessment=self.repository.public(row['payload']).model_dump(mode='json'))

    def detail(self, owner, identifier):
        with self.repository.sessions() as session:
            row = self._draft(session, owner, identifier)
            deleted = bool(row['assessment_id'] and not session.scalar(select(assessments.c.id).where(
                assessments.c.learner_id == owner, assessments.c.id == row['assessment_id'])))
            return dict(self.public(row), deleted=deleted)

    def recent(self, owner, conversation):
        with self.repository.sessions() as session:
            self._conversation(session, owner, conversation)
            rows = session.execute(select(chat_drafts).where(chat_drafts.c.learner_id == owner,
                chat_drafts.c.conversation_id == conversation).order_by(chat_drafts.c.created_at.desc()).limit(3)).mappings()
            return [self.public(row) for row in rows]

    def replay(self, owner, conversation, request):
        from app.history_management.repositories.events.postgres import request_hash
        with self.repository.sessions() as session:
            self._conversation(session, owner, conversation)
            row = session.execute(select(chat_drafts).where(chat_drafts.c.learner_id == owner,
                chat_drafts.c.operation_id == str(request.client_request_id))).mappings().first()
            if row and (row['conversation_id'] != conversation or row['payload']['fingerprint'] != request_hash(request.fingerprint_payload())):
                raise AppError('OPERATION_CONFLICT', 'Request changed.', 409)
            return self.public(row) if row else None

    def save(self, owner, conversation, request, generated, sources, claim):
        from .repositories.tables import generation_claims
        from app.history_management.repositories.events.postgres import request_hash
        with self.repository.transactions.write(owner) as tx:
            session = tx._session
            self._conversation(session, owner, conversation)
            fingerprint = request_hash(request.fingerprint_payload())
            existing = session.execute(select(chat_drafts).where(chat_drafts.c.learner_id == owner,
                chat_drafts.c.operation_id == str(request.client_request_id))).mappings().first()
            if existing:
                if existing['conversation_id'] != conversation or existing['payload']['fingerprint'] != fingerprint:
                    raise AppError('OPERATION_CONFLICT', 'Request changed.', 409)
                return self.public(existing)
            lease = session.execute(select(generation_claims).where(generation_claims.c.learner_id == owner,
                generation_claims.c.operation_id == str(request.client_request_id))).mappings().first()
            if not lease or lease['claim_id'] != claim or lease['claim_until'] <= self.repository.clock():
                raise AppError('ASSESSMENT_GENERATION_EXPIRED', 'Retry this assessment request.', 409)
            if session.scalar(select(func.count()).select_from(chat_drafts).where(chat_drafts.c.learner_id == owner)) >= 200:
                raise AppError('ASSESSMENT_DRAFT_CAPACITY', 'Remove unused chats before generating more practice.', 409)
            payload = dict(id=str(uuid4()), learner_id=owner, context_id=request.context_id, title=generated.title,
                purpose=request.purpose, revision=1, created_at=self.repository.clock().isoformat(),
                questions=[dict(q.model_dump(mode='json'), id=str(uuid4())) for q in generated.questions],
                sources=sources, operation_id=str(request.client_request_id), fingerprint=fingerprint)
            row = dict(id=str(uuid4()), learner_id=owner, conversation_id=conversation, payload=payload,
                operation_id=str(request.client_request_id), assessment_id=None, created_at=self.repository.clock())
            session.execute(chat_drafts.insert().values(**row))
            auto = session.scalar(select(preferences.c.auto_add).where(preferences.c.learner_id == owner))
            if auto: row = self._publish(session, owner, row)
            return self.public(row)

    def _publish(self, session, owner, row):
        if row['assessment_id']:
            self.repository._assessment(session, owner, row['assessment_id'])
            return row
        if session.scalar(select(func.count()).select_from(assessments).where(assessments.c.learner_id == owner)) >= 200:
            raise AppError('ASSESSMENT_CAPACITY', 'Remove unused assessments before adding more.', 409)
        payload = dict(row['payload'])
        from datetime import datetime
        payload['created_at'] = datetime.fromisoformat(payload['created_at'])
        session.execute(assessments.insert().values(**payload))
        session.execute(update(chat_drafts).where(chat_drafts.c.id == row['id']).values(assessment_id=payload['id']))
        return dict(row, assessment_id=payload['id'])

    def publish(self, owner, identifier):
        with self.repository.transactions.write(owner) as tx:
            return self.public(self._publish(tx._session, owner, self._draft(tx._session, owner, identifier)))

    def settings(self, owner):
        with self.repository.sessions() as session:
            row = session.execute(select(preferences).where(preferences.c.learner_id == owner)).mappings().first()
            return dict(auto_add=row['auto_add'], revision=row['revision']) if row else dict(auto_add=False, revision=0)

    def update_settings(self, owner, auto_add, expected_revision):
        with self.repository.transactions.write(owner) as tx:
            row = tx._session.execute(select(preferences).where(preferences.c.learner_id == owner)).mappings().first()
            revision = row['revision'] if row else 0
            if revision != expected_revision:
                raise AppError('REVISION_CONFLICT', 'Settings changed. Refresh before saving.', 409)
            values = dict(learner_id=owner, auto_add=auto_add, revision=revision+1)
            from sqlalchemy.dialects.postgresql import insert
            tx._session.execute(insert(preferences).values(**values).on_conflict_do_update(index_elements=['learner_id'], set_=values))
            return dict(auto_add=auto_add, revision=revision+1)
