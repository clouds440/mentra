"""Bounded, owner-serialized event writes; no provider calls or memory writes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid4
from sqlalchemy import select, update, delete, func, and_, or_, text
from sqlalchemy.dialects.postgresql import insert
from app.core.exceptions import AppError
from app.db.owner_transactions import OwnerTransactions
from app.history_management.events.schemas import EventDraft, ReminderRule
from app.history_management.events.temporal import bounds, reminder_due, bucket
from .errors import database_errors
from .tables import (events as e, evidence as ev, revisions as rv, preferences as p,
                     receipts as rc, suppression as sp, reminders as rm, sync_state as ss, changes as ch)

DEFAULTS = dict(automatic_events=True, reminders_enabled=True, timezone=None,
                timed_offset_minutes=1440, date_days_before=1, date_hour=9,
                date_minute=0, revision=0, disabled_since=None)


def request_hash(value):
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def conflict():
    return AppError('REVISION_CONFLICT', 'This event or preference changed. Reload it before saving your draft.', 409)


class EventRepository:
    def __init__(self, sessions, *, clock=None, capacity=1000):
        self.sessions = sessions
        self.transactions = OwnerTransactions(sessions)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.capacity = capacity

    def _state(self, session, owner):
        row = session.execute(select(ss).where(ss.c.learner_id == owner)).mappings().first()
        return dict(row) if row else dict(revision=0, floor=0)

    def _change(self, session, owner, entity, identifier=None, deleted=False):
        return self._change_many(session, owner, [(entity, identifier, deleted)])

    def _change_many(self, session, owner, entities):
        if not entities:
            return self._state(session, owner)['revision']
        session.execute(insert(ss).values(learner_id=owner, revision=0, floor=0).on_conflict_do_nothing())
        state = self._state(session, owner)
        revision = state['revision'] + len(entities)
        floor = max(state['floor'], revision - 10000)
        session.execute(update(ss).where(ss.c.learner_id == owner).values(revision=revision, floor=floor))
        stamp = self.clock()
        session.execute(ch.insert(), [dict(learner_id=owner, revision=state['revision']+index,
            entity=entity, entity_id=identifier, deleted=deleted, created_at=stamp)
            for index, (entity, identifier, deleted) in enumerate(entities, 1)])
        if floor > state['floor']:
            session.execute(delete(ch).where(ch.c.learner_id == owner, ch.c.revision <= floor))
        return revision

    def _preferences(self, session, owner):
        row = session.execute(select(p).where(p.c.learner_id == owner)).mappings().first()
        values = dict(row) if row else dict(DEFAULTS)
        values.pop('learner_id', None)
        return values

    @database_errors
    def preferences(self, owner):
        with self.sessions() as session, session.begin():
            self._snapshot(session)
            return dict(self._preferences(session, owner), sync_revision=self._state(session, owner)['revision'])

    @database_errors
    def set_preferences(self, owner, body):
        with self.transactions.write(owner) as uow:
            session = uow._session
            values = self._preferences(session, owner)
            previous_enabled = values['reminders_enabled']
            if values['revision'] != body.expected_revision:
                raise conflict()
            changed = body.model_dump(exclude_unset=True, exclude={'expected_revision'})
            values.update(changed)
            values['revision'] += 1
            if not values['reminders_enabled'] and previous_enabled:
                values['disabled_since'] = self.clock()
            # Re-enabling never rearms skipped ledgers. Worker outage windows
            # remain represented by the skipped durable state, not a UI flag.
            if body.expected_revision == 0:
                session.execute(p.insert().values(learner_id=owner, **values))
            else:
                session.execute(update(p).where(p.c.learner_id == owner).values(**values))
            changed_entities = [('preferences', None, False)]
            if values['reminders_enabled'] != previous_enabled:
                # Future due times remain eligible after re-enable. Missed due
                # times are fenced here even when no worker ran while disabled.
                missed = [rm.c.learner_id == owner, rm.c.state == 'pending', rm.c.due_at <= self.clock()]
                identifiers = list(session.scalars(update(rm).where(*missed)
                    .values(state='skipped', schedule_version=rm.c.schedule_version + 1).returning(rm.c.event_id)))
                if identifiers:
                    rows = session.execute(update(e).where(e.c.learner_id == owner, e.c.id.in_(identifiers))
                        .values(revision=e.c.revision + 1, updated_at=self.clock()).returning(e.c.id, e.c.revision)).mappings().all()
                    self._audit_many(session, owner, rows, ['reminder_state'], 'preferences')
                    changed_entities.extend(('event', identifier, False) for identifier in sorted(identifiers))
            self._change_many(session, owner, changed_entities)
            return dict(values, sync_revision=self._state(session, owner)['revision'])

    def _get(self, session, owner, identifier):
        row = session.execute(select(e).where(e.c.learner_id == owner, e.c.id == identifier)).mappings().first()
        if not row:
            raise AppError('EVENT_NOT_FOUND', 'Event not found.', 404)
        return dict(row)

    def _public(self, row, ledger, stamp=None):
        value = {key: item for key, item in dict(row).items() if key not in ('learner_id', 'sort_at', 'cutoff_at', 'reminder_rule')}
        return dict(value, reminder=row['reminder_rule'], bucket=bucket(row, stamp or self.clock()),
                    reminder_state=ledger['state'], reminder_due_at=ledger['due_at'],
                    reminder_delivered_at=ledger['delivered_at'])

    def _projection(self, session, owner, row):
        ledger = session.execute(select(rm).where(rm.c.learner_id == owner, rm.c.event_id == row['id'])).mappings().one()
        return self._public(row, ledger)

    @database_errors
    def detail(self, owner, identifier):
        with self.sessions() as session, session.begin():
            self._snapshot(session)
            result = self._projection(session, owner, self._get(session, owner, identifier))
            result['evidence'] = [dict(quote=row['quote'], source_date=row['source_date'], source_timezone=row['source_timezone'],
                source_deleted=row['source_deleted'], conversation_id=row['conversation_id'], message_id=row['message_id'])
                for row in session.execute(select(ev).where(ev.c.learner_id == owner, ev.c.event_id == identifier)
                                           .order_by(ev.c.source_date.desc(), ev.c.id).limit(5)).mappings()]
            return result

    def _receipt(self, session, owner, operation, fingerprint=None):
        row = session.execute(select(rc).where(rc.c.learner_id == owner, rc.c.operation_id == operation)).mappings().first()
        if row and fingerprint is not None and row['request_hash'] != fingerprint:
            raise AppError('OPERATION_CONFLICT', 'This request ID was used for a different action.', 409)
        return row

    def _outcome(self, session, owner, receipt):
        row = session.execute(select(e).where(e.c.learner_id == owner, e.c.id == receipt['event_id'])).mappings().first()
        return dict(outcome=receipt['outcome'] if row else 'deleted', event_id=receipt['event_id'],
                    event=self._projection(session, owner, row) if row else None,
                    sync_revision=self._state(session, owner)['revision'])

    @database_errors
    def operation(self, owner, identifier):
        with self.sessions() as session, session.begin():
            self._snapshot(session)
            receipt = self._receipt(session, owner, identifier)
            if not receipt:
                raise AppError('OPERATION_NOT_FOUND', 'Operation not found.', 404)
            return self._outcome(session, owner, receipt)

    @database_errors
    def replay(self, owner, operation, payload):
        with self.sessions() as session, session.begin():
            self._snapshot(session)
            receipt = self._receipt(session, owner, operation, request_hash(payload))
            return self._outcome(session, owner, receipt) if receipt else None

    def _record_receipt(self, session, owner, operation, fingerprint, identifier, outcome, revision):
        values = dict(learner_id=owner, operation_id=operation, request_hash=fingerprint,
                      event_id=identifier, outcome=outcome, sync_revision=revision, created_at=self.clock())
        session.execute(rc.insert().values(**values))
        return self._outcome(session, owner, values)

    def _values(self, draft):
        start, cutoff = bounds(draft)
        return dict(title=draft.title, description=draft.description, kind=draft.kind, context_id=draft.context_id, timezone=draft.timezone,
                    local_date=draft.local_date, starts_at=start if draft.starts_at else None,
                    ends_at=draft.ends_at.astimezone(timezone.utc) if draft.ends_at else None,
                    sort_at=start, cutoff_at=cutoff, reminder_rule=draft.reminder.model_dump(mode='json'))

    def _audit(self, session, owner, identifier, revision, fields, actor='manual'):
        self._audit_many(session, owner, [dict(id=identifier, revision=revision)], fields, actor)

    def _audit_many(self, session, owner, rows, fields, actor):
        if rows:
            stamp = self.clock()
            session.execute(rv.insert(), [dict(learner_id=owner, event_id=row['id'], revision=row['revision'],
                actor=actor, changed_fields=sorted(fields), created_at=stamp) for row in rows])

    @database_errors
    def create(self, owner, body):
        operation = str(body.client_request_id)
        fingerprint = request_hash(['create', body.model_dump(mode='json', exclude={'client_request_id'})])
        with self.transactions.write(owner) as uow:
            session = uow._session
            receipt = self._receipt(session, owner, operation, fingerprint)
            if receipt:
                return self._outcome(session, owner, receipt)
            if session.scalar(select(func.count()).select_from(e).where(e.c.learner_id == owner)) >= self.capacity:
                raise AppError('CAPACITY', 'Your event limit has been reached. Delete unused events before adding another.', 409)
            identifier, now = str(uuid4()), self.clock()
            values = dict(id=identifier, learner_id=owner, **self._values(body), status='scheduled', origin='manual',
                          revision=1, created_at=now, updated_at=now, completed_at=None)
            due, state = reminder_due(body, self._preferences(session, owner), now)
            session.execute(e.insert().values(**values))
            session.execute(rm.insert().values(learner_id=owner, event_id=identifier, due_at=due,
                            state=state, schedule_version=1, delivered_at=None, receipt_id=None))
            self._audit(session, owner, identifier, 1, ['created'])
            revision = self._change(session, owner, 'event', identifier)
            return self._record_receipt(session, owner, operation, fingerprint, identifier, 'saved', revision)

    @database_errors
    def edit(self, owner, identifier, body):
        operation = str(body.client_request_id)
        fingerprint = request_hash(['edit', identifier, body.model_dump(mode='json', exclude={'client_request_id'})])
        with self.transactions.write(owner) as uow:
            session = uow._session
            receipt = self._receipt(session, owner, operation, fingerprint)
            if receipt:
                return self._outcome(session, owner, receipt)
            row = self._get(session, owner, identifier)
            if row['revision'] != body.expected_revision:
                raise conflict()
            ledger = session.execute(select(rm).where(rm.c.learner_id == owner, rm.c.event_id == identifier)).mappings().one()
            details = body.details or EventDraft(**{key: row[key] for key in ('title', 'description', 'kind', 'context_id', 'timezone', 'local_date', 'starts_at', 'ends_at')}, reminder=row['reminder_rule'])
            values = self._values(details)
            status = body.status or row['status']
            now = self.clock()
            changed_fields = [key for key, value in values.items() if row[key] != value]
            reminder_changed = ReminderRule.model_validate(row['reminder_rule']) != details.reminder
            if not reminder_changed and 'reminder_rule' in changed_fields:
                changed_fields.remove('reminder_rule')
            if status != row['status']:
                changed_fields.append('status')
            if ledger['state'] == 'delivered' and reminder_changed:
                raise AppError('REMINDER_ALREADY_SENT', 'This event has already received its one reminder.', 409)
            values.update(status=status, revision=row['revision']+1, updated_at=now,
                          completed_at=(row['completed_at'] or now) if status == 'completed' else None)
            session.execute(update(e).where(e.c.learner_id == owner, e.c.id == identifier).values(**values))
            if ledger['state'] != 'delivered':
                schedule_changed = any(key in changed_fields for key in ('local_date', 'starts_at', 'reminder_rule')) or (
                    details.local_date is not None and 'timezone' in changed_fields)
                if status != 'scheduled':
                    due = reminder_due(details, self._preferences(session, owner), now)[0] if schedule_changed else ledger['due_at']
                    state = 'cancelled'
                elif schedule_changed:
                    due, state = reminder_due(details, self._preferences(session, owner), now)
                elif row['status'] != 'scheduled':
                    due = ledger['due_at']
                    state = 'cancelled' if details.reminder.mode == 'disabled' else (
                        'pending' if due is not None and due > now else 'skipped')
                else:
                    due, state = ledger['due_at'], ledger['state']
                if due != ledger['due_at'] or state != ledger['state']:
                    session.execute(update(rm).where(rm.c.learner_id == owner, rm.c.event_id == identifier)
                                    .values(due_at=due, state=state, schedule_version=ledger['schedule_version']+1))
            self._audit(session, owner, identifier, values['revision'], changed_fields)
            revision = self._change(session, owner, 'event', identifier)
            return self._record_receipt(session, owner, operation, fingerprint, identifier, 'updated', revision)

    @database_errors
    def remove(self, owner, identifier, revision, operation):
        fingerprint = request_hash(['delete', identifier, revision])
        with self.transactions.write(owner) as uow:
            session = uow._session
            receipt = self._receipt(session, owner, operation, fingerprint)
            if receipt:
                return self._outcome(session, owner, receipt)
            row = self._get(session, owner, identifier)
            if row['revision'] != revision:
                raise conflict()
            hashes = [request_hash(['event', identifier])]
            for item in session.execute(select(ev.c.message_id, ev.c.quote).where(ev.c.learner_id == owner, ev.c.event_id == identifier)).mappings():
                hashes.append(request_hash(['evidence', item['message_id'], item['quote']]))
            for digest in hashes:
                session.execute(insert(sp).values(learner_id=owner, fingerprint=digest, created_at=self.clock()).on_conflict_do_nothing())
            session.execute(delete(e).where(e.c.learner_id == owner, e.c.id == identifier))
            watermark = self._change(session, owner, 'event', identifier, True)
            return self._record_receipt(session, owner, operation, fingerprint, identifier, 'deleted', watermark)

    @staticmethod
    def _snapshot(session):
        # A page and its watermark must see the same committed snapshot.
        session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))

    def _rows(self, session, owner, identifiers, stamp=None):
        if not identifiers:
            return {}
        rows = session.execute(select(e, rm.c.state.label('reminder_state'), rm.c.due_at,
                    rm.c.delivered_at).join(rm, and_(rm.c.learner_id == e.c.learner_id, rm.c.event_id == e.c.id))
                    .where(e.c.learner_id == owner, e.c.id.in_(identifiers))).mappings().all()
        stamp = stamp or self.clock()
        return {row['id']: self._public({key: row[key] for key in e.c.keys()},
                                      dict(state=row['reminder_state'], due_at=row['due_at'], delivered_at=row['delivered_at']), stamp) for row in rows}

    @database_errors
    def list(self, owner, filters, cursor=None, limit=30):
        binding = request_hash([owner, filters])
        with self.sessions() as session, session.begin():
            self._snapshot(session)
            stamp_now = self.clock()
            watermark = self._state(session, owner)['revision']
            query = select(e.c.id, e.c.sort_at).where(e.c.learner_id == owner,
                          e.c.sort_at >= filters['after'], e.c.sort_at < filters['before'])
            if filters.get('status'):
                query = query.where(e.c.status == filters['status'])
            if filters.get('kind'):
                query = query.where(e.c.kind == filters['kind'])
            if filters.get('query'):
                query = query.where(e.c.title.icontains(filters['query'], autoescape=True))
            if cursor:
                try:
                    token = json.loads(cursor)
                    stamp = datetime.fromisoformat(token['at'])
                    identifier = str(UUID(token['id']))
                    if stamp.tzinfo is None or token['filter'] != binding:
                        raise ValueError()
                    if token['revision'] != watermark:
                        raise AppError('PAGE_CHANGED', 'The agenda changed. Reload this page.', 409)
                except (ValueError, KeyError, TypeError):
                    raise AppError('INVALID_CURSOR', 'Invalid event page cursor.', 422) from None
                query = query.where(or_(e.c.sort_at > stamp, and_(e.c.sort_at == stamp, e.c.id > identifier)))
            rows = session.execute(query.order_by(e.c.sort_at, e.c.id).limit(limit+1)).mappings().all()
            more = len(rows) > limit
            rows = rows[:limit]
            projections = self._rows(session, owner, [row['id'] for row in rows], stamp_now)
            next_cursor = json.dumps(dict(at=rows[-1]['sort_at'].isoformat(), id=rows[-1]['id'], filter=binding, revision=watermark)) if more else None
            return dict(items=[projections[row['id']] for row in rows], next_cursor=next_cursor,
                        has_more=more, sync_revision=watermark, server_time=stamp_now)

    @database_errors
    def sync(self, owner, after, limit=100):
        with self.sessions() as session, session.begin():
            self._snapshot(session)
            stamp_now = self.clock()
            state = self._state(session, owner)
            if after < state['floor'] or after > state['revision']:
                return dict(items=[], next_cursor=state['revision'], reset=True, floor=state['floor'], has_more=False, server_time=stamp_now)
            rows = session.execute(select(ch).where(ch.c.learner_id == owner, ch.c.revision > after)
                                   .order_by(ch.c.revision).limit(limit+1)).mappings().all()
            more = len(rows) > limit
            rows = rows[:limit]
            projections = self._rows(session, owner, [row['entity_id'] for row in rows if row['entity'] == 'event'], stamp_now)
            preferences = dict(self._preferences(session, owner), sync_revision=state['revision'])
            items = [dict(revision=row['revision'], entity=row['entity'], id=row['entity_id'],
                          deleted=row['entity'] == 'event' and row['entity_id'] not in projections,
                          event=projections.get(row['entity_id']), preferences=preferences if row['entity'] == 'preferences' else None) for row in rows]
            return dict(items=items, next_cursor=rows[-1]['revision'] if more else state['revision'],
                        has_more=more, reset=False, floor=state['floor'], server_time=stamp_now)

    @database_errors
    def summary(self, owner):
        with self.sessions() as session, session.begin():
            self._snapshot(session)
            now = self.clock()
            upcoming = session.scalar(select(func.count()).select_from(e).where(e.c.learner_id == owner,
                e.c.status == 'scheduled', or_(and_(e.c.kind.in_(['assignment', 'deadline']), e.c.cutoff_at > now),
                                              and_(e.c.kind.not_in(['assignment', 'deadline']), e.c.sort_at > now))))
            return dict(upcoming=upcoming, sync_revision=self._state(session, owner)['revision'], server_time=now)

    @staticmethod
    def detach_chat(session, owner, conversation_id):
        """Saved events survive source deletion; mark evidence in the same lock."""
        identifiers = list(session.scalars(select(ev.c.event_id).where(ev.c.learner_id == owner, ev.c.conversation_id == conversation_id).distinct()))
        session.execute(update(ev).where(ev.c.learner_id == owner, ev.c.conversation_id == conversation_id).values(source_deleted=True))
        adapter = EventRepository(None)
        if identifiers:
            rows = session.execute(update(e).where(e.c.learner_id == owner, e.c.id.in_(identifiers))
                .values(revision=e.c.revision+1, updated_at=adapter.clock()).returning(e.c.id, e.c.revision)).mappings().all()
            adapter._audit_many(session, owner, rows, ['source_deleted'], 'source_deleted')
            adapter._change_many(session, owner, [('event', identifier, False) for identifier in sorted(identifiers)])
