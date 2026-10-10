from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, func, and_, or_, text
from sqlalchemy.dialects.postgresql import insert
from app.core.exceptions import AppError
from app.db.owner_transactions import OwnerTransactions
from .tables import inbox as n, receipts as r, preferences as p, state as s, changes as c


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={
    'publish': {'result': lambda value: dict(domain_status=value['outcome']), 'outcome': lambda value: 'skipped' if value['outcome'] == 'disabled' else 'success'},
})
class NotificationRepository:
    def __init__(self, sessions, clock=None):
        self.sessions, self.transactions = sessions, OwnerTransactions(sessions)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _preferences(self, session, owner):
        row = session.execute(select(p).where(p.c.learner_id == owner)).mappings().first()
        return dict(row) if row else dict(enabled=True, disabled_kinds=[], resume_after=None, kind_resume_after={}, revision=0)

    def preferences(self, owner):
        with self.sessions() as session: return self._preferences(session, owner)

    def _change(self, session, owner, identifier=None, deleted=False):
        session.execute(insert(s).values(learner_id=owner, revision=0, floor=0).on_conflict_do_nothing())
        row = session.execute(select(s).where(s.c.learner_id == owner)).mappings().one()
        revision, floor = row['revision'] + 1, max(0, row['revision'] + 1 - 10000)
        session.execute(update(s).where(s.c.learner_id == owner).values(revision=revision, floor=floor))
        session.execute(c.insert().values(learner_id=owner, revision=revision, notification_id=identifier, deleted=deleted))
        if floor > row['floor']:
            session.execute(delete(c).where(c.c.learner_id == owner, c.c.revision <= floor))
        return revision

    def set_preferences(self, owner, body):
        with self.transactions.write(owner) as transaction:
            session = transaction._session
            current = self._preferences(session, owner)
            if current['revision'] != body.expected_revision:
                raise AppError('REVISION_CONFLICT', 'Notification settings changed. Reload them before saving.', 409)
            resumed = current['resume_after']
            stamp = self.clock()
            if body.enabled and not current['enabled']: resumed = stamp
            per_kind = dict(current['kind_resume_after'])
            for kind in set(current['disabled_kinds']) - set(body.disabled_kinds): per_kind[kind] = stamp.isoformat()
            values = dict(enabled=body.enabled, disabled_kinds=body.disabled_kinds, resume_after=resumed,
                kind_resume_after=per_kind, revision=current['revision']+1)
            session.execute(insert(p).values(learner_id=owner, **values).on_conflict_do_update(index_elements=[p.c.learner_id], set_=values))
            self._change(session, owner)
            return values

    def publish(self, transaction, draft):
        session, owner = transaction._session, transaction.owner
        previous = session.execute(select(r.c.notification_id).where(r.c.learner_id == owner,
            r.c.producer == draft.producer, r.c.delivery_key == draft.delivery_key)).scalar_one_or_none()
        if previous:
            return dict(outcome='already_delivered', notification_id=previous)
        preferences = self._preferences(session, owner)
        kind_after = preferences['kind_resume_after'].get(draft.kind)
        if (not preferences['enabled'] or draft.kind in preferences['disabled_kinds']
            or preferences['resume_after'] is not None and draft.due_at <= preferences['resume_after']
            or kind_after and draft.due_at <= datetime.fromisoformat(kind_after)):
            return dict(outcome='disabled', notification_id=None)
        # Bounded pruning never erases the lifetime producer receipt.
        old = list(session.execute(select(n.c.id).where(n.c.learner_id == owner,
            n.c.created_at < self.clock() - timedelta(days=90),
            or_(n.c.read_at.is_not(None), n.c.dismissed_at.is_not(None))).limit(100)).scalars())
        for identifier in old:
            session.execute(delete(n).where(n.c.id == identifier, n.c.learner_id == owner))
            self._change(session, owner, identifier, True)
        if session.scalar(select(func.count()).select_from(n).where(n.c.learner_id == owner)) >= 1000:
            raise AppError('NOTIFICATION_CAPACITY', 'The notification inbox is full.', 409)
        identifier, stamp = str(uuid4()), self.clock()
        session.execute(n.insert().values(id=identifier, learner_id=owner, kind=draft.kind, title=draft.title,
            body=draft.body, target_kind=draft.target_kind, target_id=str(draft.target_id) if draft.target_id else None,
            created_at=stamp, revision=1))
        session.execute(r.insert().values(learner_id=owner, producer=draft.producer, delivery_key=draft.delivery_key,
            notification_id=identifier, created_at=stamp))
        self._change(session, owner, identifier)
        return dict(outcome='delivered', notification_id=identifier)

    def inbox(self, owner, *, unread=False, before=None, limit=30):
        limit = max(1, min(50, limit))
        with self.sessions.begin() as session:
            session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            query = select(n).where(n.c.learner_id == owner, n.c.dismissed_at.is_(None))
            if unread: query = query.where(n.c.read_at.is_(None))
            if before:
                anchor = session.execute(select(n).where(n.c.id == before, n.c.learner_id == owner)).mappings().first()
                if not anchor: raise AppError('NOTIFICATION_CURSOR_EXPIRED', 'Reload the notification list.', 409)
                query = query.where(or_(n.c.created_at < anchor['created_at'], and_(n.c.created_at == anchor['created_at'], n.c.id < before)))
            rows = [dict(row) for row in session.execute(query.order_by(n.c.created_at.desc(), n.c.id.desc()).limit(limit+1)).mappings()]
            unread_count = session.scalar(select(func.count()).select_from(n).where(n.c.learner_id == owner, n.c.read_at.is_(None), n.c.dismissed_at.is_(None)))
            revision = session.scalar(select(s.c.revision).where(s.c.learner_id == owner)) or 0
            return dict(items=rows[:limit], next_cursor=rows[limit-1]['id'] if len(rows)>limit else None,
                unread_count=unread_count, sync_revision=revision)

    def edit(self, owner, identifier, body):
        with self.transactions.write(owner) as transaction:
            session = transaction._session
            row = session.execute(select(n).where(n.c.id == identifier, n.c.learner_id == owner)).mappings().first()
            if not row: raise AppError('NOTIFICATION_NOT_FOUND', 'Notification unavailable.', 404)
            field = 'read_at' if body.action == 'read' else 'dismissed_at'
            if row[field] is not None: return dict(row)
            if row['revision'] != body.expected_revision:
                raise AppError('REVISION_CONFLICT', 'This notification changed. Reload before editing.', 409)
            values = {field:self.clock(), 'revision':row['revision']+1}
            session.execute(update(n).where(n.c.id == identifier, n.c.learner_id == owner).values(**values))
            self._change(session, owner, identifier, body.action == 'dismiss')
            return dict(row, **values)

    def remove_target(self, transaction, target_kind, target_id):
        session, owner = transaction._session, transaction.owner
        ids = list(session.execute(select(n.c.id).where(n.c.learner_id == owner, n.c.target_kind == target_kind, n.c.target_id == target_id)).scalars())
        for identifier in ids:
            session.execute(delete(n).where(n.c.learner_id == owner, n.c.id == identifier))
            self._change(session, owner, identifier, True)

    def sync(self, owner, after):
        with self.sessions.begin() as session:
            session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            row = session.execute(select(s).where(s.c.learner_id == owner)).mappings().first() or dict(revision=0, floor=0)
            if after < row['floor'] or after > row['revision']:
                return dict(reset=True, cursor=row['revision'], items=[], has_more=False)
            changes = [dict(value) for value in session.execute(select(c).where(c.c.learner_id == owner,
                c.c.revision > after).order_by(c.c.revision).limit(101)).mappings()]
            return dict(reset=False, cursor=changes[min(len(changes),100)-1]['revision'] if changes else row['revision'],
                items=changes[:100], has_more=len(changes)>100)
