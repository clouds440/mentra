"""Durable chat organization. Admit once; process one chat per short transaction."""
from hashlib import sha256
import json
from sqlalchemy import select, update, func
from sqlalchemy.exc import DBAPIError
from app.core.exceptions import AppError
from .tables import conversations as c, management_jobs as jobs
from .postgres import now, conflict


class ChatManagement:
    def __init__(self, repository):
        self.repository = repository
        self.sessions = repository.sessions

    @staticmethod
    def public(row):
        return {key: row[key] for key in ('id', 'action', 'items', 'completed_ids', 'failed_items', 'state', 'created_at', 'updated_at')}

    def organize(self, owner, identifier, body):
        with self.sessions.begin() as session:
            state = self.repository._sync_lock(session, owner)
            row = self.repository._conversation(session, owner, identifier, True)
            if row['revision'] != body.expected_revision:
                raise conflict()
            if row['pending_action']:
                raise AppError('CHAT_ACTION_PENDING', 'This chat has a pending action. Wait for it to finish.', 409)
            values = dict(revision=row['revision'] + 1)
            if body.pinned is not None:
                if body.pinned and row['archived_at']:
                    raise AppError('CHAT_ARCHIVED', 'Unarchive this chat before pinning it.', 409)
                if body.pinned and not row['pinned_at'] and session.scalar(select(func.count()).select_from(c).where(c.c.learner_id == owner, c.c.deleted_at.is_(None), c.c.pinned_at.is_not(None))) >= 100:
                    raise AppError('CHAT_PIN_LIMIT', 'Unpin a chat before pinning another. You can pin up to 100 chats.', 409)
                values['pinned_at'] = (row['pinned_at'] or now()) if body.pinned else None
            else:
                values['archived_at'] = (row['archived_at'] or now()) if body.archived else None
                if body.archived:
                    values['pinned_at'] = None
            session.execute(update(c).where(c.c.id == identifier, c.c.learner_id == owner).values(**values))
            self.repository._change(session, owner, identifier, state)
            return dict(row, **values)

    def enqueue(self, owner, body):
        identifier = str(body.client_request_id)
        items = sorted((item.model_dump(mode='json') for item in body.items), key=lambda item: item['conversation_id'])
        fingerprint = sha256(json.dumps([body.action, items], sort_keys=True).encode()).hexdigest()
        with self.sessions.begin() as session:
            state = self.repository._sync_lock(session, owner)
            existing = session.execute(select(jobs).where(jobs.c.id == identifier)).mappings().first()
            if existing:
                if existing['learner_id'] != owner:
                    raise AppError('CHAT_ACTION_NOT_FOUND', 'Chat action not found.', 404)
                if existing['request_hash'] != fingerprint:
                    raise AppError('CHAT_ACTION_CONFLICT', 'This action ID was already used for a different selection.', 409)
                return self.public(existing)
            if session.scalar(select(func.count()).select_from(jobs).where(jobs.c.learner_id == owner, jobs.c.state != 'completed')) >= 10:
                raise AppError('CHAT_ACTION_LIMIT', 'Wait for earlier chat actions to finish before starting another.', 409)
            rows = list(session.execute(select(c).where(c.c.learner_id == owner, c.c.id.in_([item['conversation_id'] for item in items]), c.c.deleted_at.is_(None)).order_by(c.c.id).with_for_update()).mappings())
            if len(rows) != len(items):
                raise AppError('CHAT_NOT_FOUND', 'One or more chats are unavailable. Refresh your chats and try again.', 404)
            revisions = {item['conversation_id']: item['expected_revision'] for item in items}
            if any(row['revision'] != revisions[row['id']] or row['pending_action'] for row in rows):
                raise conflict()
            stamp = now()
            job = dict(id=identifier, learner_id=owner, request_hash=fingerprint, action=body.action, items=items,
                completed_ids=[], failed_items=[], state='queued', created_at=stamp, updated_at=stamp)
            session.execute(jobs.insert().values(**job))
            for row in rows:
                session.execute(update(c).where(c.c.id == row['id']).values(pending_action=body.action, pending_action_id=identifier, revision=row['revision'] + 1))
                self.repository._change(session, owner, row['id'], state)
                state = dict(state, revision=state['revision'] + 1)
            return self.public(job)

    def status(self, owner, identifier):
        with self.sessions() as session:
            row = session.execute(select(jobs).where(jobs.c.id == identifier, jobs.c.learner_id == owner)).mappings().first()
            if not row:
                raise AppError('CHAT_ACTION_NOT_FOUND', 'Chat action not found.', 404)
            return self.public(row)

    def run_once(self):
        from app.db.owner_transactions import OwnerTransactions
        with self.sessions() as session:
            candidates = list(session.execute(select(jobs.c.id, jobs.c.learner_id).where(jobs.c.state != 'completed').order_by(jobs.c.updated_at, jobs.c.id).limit(10)))
        for identifier, owner in candidates:
            with OwnerTransactions(self.sessions, timeout_ms=30000).try_write(owner) as work:
                if not work:
                    continue
                session = work._session
                job = session.execute(select(jobs).where(jobs.c.id == identifier, jobs.c.state != 'completed').with_for_update(skip_locked=True)).mappings().first()
                if not job:
                    continue
                finished = set(job['completed_ids']) | {item['conversation_id'] for item in job['failed_items']}
                item = next((item for item in job['items'] if item['conversation_id'] not in finished), None)
                if not item:
                    session.execute(update(jobs).where(jobs.c.id == identifier).values(state='completed', updated_at=now()))
                    return True
                cid = item['conversation_id']
                row = session.execute(select(c).where(c.c.id == cid, c.c.learner_id == owner).with_for_update()).mappings().first()
                state = self.repository._sync_lock(session, owner)
                completed, failed = list(job['completed_ids']), list(job['failed_items'])
                try:
                    with session.begin_nested():
                        if not row or row['deleted_at'] or row['pending_action_id'] != identifier:
                            raise AppError('CHAT_ACTION_CHANGED', 'This chat changed before the action could finish. Refresh and review it.', 409)
                        if job['action'] == 'delete':
                            self.repository._edit_in_session(session, owner, dict(row), state, remove=True)
                        else:
                            values = dict(archived_at=now() if job['action'] == 'archive' else None,
                                pending_action=None, pending_action_id=None, revision=row['revision'] + 1)
                            if job['action'] == 'archive':
                                values['pinned_at'] = None
                            session.execute(update(c).where(c.c.id == cid, c.c.learner_id == owner).values(**values))
                            self.repository._change(session, owner, cid, state)
                    completed.append(cid)
                except (AppError, DBAPIError) as error:
                    message = error.message if isinstance(error, AppError) else 'This chat could not be updated. Its contents were kept; refresh and retry.'
                    failed.append(dict(conversation_id=cid, error=message))
                    if row and not row['deleted_at'] and row['pending_action_id'] == identifier:
                        session.execute(update(c).where(c.c.id == cid).values(pending_action=None, pending_action_id=None, revision=row['revision'] + 1))
                        self.repository._change(session, owner, cid, state)
                # A DB/process failure rolls back both content and receipt; the next worker retries.
                session.execute(update(jobs).where(jobs.c.id == identifier).values(completed_ids=completed, failed_items=failed,
                    state='completed' if len(completed) + len(failed) == len(job['items']) else 'running', updated_at=now()))
                return True
        return False
