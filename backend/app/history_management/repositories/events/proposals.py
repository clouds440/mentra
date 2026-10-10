from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, func
from app.core.exceptions import AppError
from app.db.owner_transactions import OwnerTransactions
from app.chat.repositories.tables import conversations, messages, turns
from app.langchain.repositories.checkpoint_tables import delete_thread
from app.history_management.events.schemas import EventCreate, EventEdit, EventDraft
from app.history_management.events.proposals import EventProposal
from .proposal_tables import proposals as p
from .postgres import request_hash, conflict
from .tables import events, evidence, suppression


def thread_id(owner, identifier):
    return f'event-confirmation-v1:{owner}:{identifier}'


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class EventProposalRepository:
    def __init__(self, sessions, events_repository, clock=None):
        self.sessions, self.events = sessions, events_repository
        self.transactions = OwnerTransactions(sessions)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _public(self, row):
        return EventProposal(**row['payload'], id=row['id'], revision=row['revision'], state=row['state'],
            quote=row['quote'], source_date=row['source_date'], conversation_id=row['conversation_id'],
            expires_at=row['expires_at'], event_id=row['event_id'])

    def _get(self, session, owner, identifier):
        row = session.execute(select(p).where(p.c.learner_id == owner, p.c.id == identifier)).mappings().first()
        if not row: raise AppError('PROPOSAL_NOT_FOUND', 'Event proposal unavailable.', 404)
        return dict(row)

    def _source(self, session, owner, row):
        source = session.execute(select(messages).join(conversations,
            (messages.c.learner_id == conversations.c.learner_id) & (messages.c.conversation_id == conversations.c.id))
            .where(messages.c.learner_id == owner, messages.c.id == row['message_id'],
                   messages.c.role == 'user', conversations.c.deleted_at.is_(None))).mappings().first()
        if not source or row['quote'] not in source['content']:
            raise AppError('PROPOSAL_SOURCE_EXPIRED', 'This proposal no longer has an available source.', 409)
        return source

    def create(self, owner, body, scope):
        digest = request_hash([str(body.message_id), body.quote, body.model_dump(mode='json')])
        with self.transactions.write(owner) as tx:
            session, now = tx._session, self.clock()
            turn = session.execute(select(turns).where(turns.c.learner_id == owner,
                turns.c.id == scope['turn_id'])).mappings().first()
            if not turn or turn['state'] != 'RUNNING' or turn['attempt'] != scope['attempt'] or turn['lease_until'] <= now:
                raise AppError('CHAT_ATTEMPT_EXPIRED', 'This response is no longer running.', 409)
            if str(body.message_id) not in scope['evidence_ids']:
                raise AppError('PROPOSAL_EVIDENCE_INVALID', 'Use an exact visible user statement.', 422)
            source = self._source(session, owner, dict(message_id=str(body.message_id), quote=body.quote))
            if source['conversation_id'] != scope['conversation_id']:
                raise AppError('PROPOSAL_EVIDENCE_INVALID', 'Event admission requires evidence from this conversation.', 422)
            if not self.events._preferences(session, owner)['automatic_events']:
                return dict(outcome='rejected', reason='Automatic event capture is disabled.')
            previous = session.execute(select(p).where(p.c.learner_id == owner, p.c.fingerprint == digest)).mappings().first()
            if previous: return dict(outcome='awaiting_confirmation' if previous['state'] in ('pending', 'deciding') else 'already_known', proposal=self._public(previous).model_dump(mode='json'))
            suppressed = session.execute(select(suppression.c.fingerprint).where(suppression.c.learner_id == owner,
                suppression.c.fingerprint == request_hash(['evidence', str(body.message_id), body.quote]))).first()
            if suppressed: return dict(outcome='rejected', reason='This event statement was previously removed.')
            if body.target_id is not None:
                target = self.events._get(session, owner, str(body.target_id))
                if target['revision'] != body.target_revision: raise conflict()
            self._prune(session, owner)
            if session.scalar(select(func.count()).select_from(p).where(p.c.learner_id == owner, p.c.state.in_(['pending', 'deciding']))) >= 30:
                raise AppError('PROPOSAL_CAPACITY', 'Review your pending event proposals before adding more.', 409)
            payload = body.model_dump(mode='json', exclude={'message_id', 'quote'})
            identifier = str(uuid4())
            session.execute(p.insert().values(id=identifier, learner_id=owner, conversation_id=source['conversation_id'],
                message_id=str(body.message_id), turn_id=turn['id'], attempt=turn['attempt'], fingerprint=digest,
                payload=payload, quote=body.quote, source_date=source['created_at'], source_timezone=payload['candidate'].get('timezone') if payload['candidate'] else None,
                workflow_version='event-confirmation-v1', state='pending', revision=1, created_at=now, expires_at=now+timedelta(days=7)))
            return dict(outcome='awaiting_confirmation', proposal=self._public(self._get(session, owner, identifier)).model_dump(mode='json'))

    def _prune(self, session, owner):
        expired = list(session.execute(select(p.c.id).where(p.c.learner_id == owner,
            p.c.expires_at <= self.clock(), p.c.state.in_(['pending', 'deciding'])).limit(30)).scalars())
        for identifier in expired:
            session.execute(update(p).where(p.c.id == identifier).values(state='expired', revision=p.c.revision+1, decision=None, claim_id=None, claim_until=None))
            delete_thread(session, thread_id(owner, identifier))
        old = list(session.execute(select(p.c.id).where(p.c.learner_id == owner,
            p.c.state.not_in(['pending', 'deciding']), p.c.created_at < self.clock()-timedelta(days=30)).limit(100)).scalars())
        for identifier in old:
            delete_thread(session, thread_id(owner, identifier))
            session.execute(delete(p).where(p.c.id == identifier))

    def list(self, owner, conversation_id=None):
        with self.transactions.write(owner) as tx:
            self._prune(tx._session, owner)
            query = select(p).where(p.c.learner_id == owner, p.c.state.in_(['pending', 'deciding']))
            if conversation_id: query = query.where(p.c.conversation_id == conversation_id)
            return [self._public(row) for row in tx._session.execute(query.order_by(p.c.created_at.desc()).limit(30)).mappings()]

    def detail(self, owner, identifier):
        with self.sessions() as session: return self._public(self._get(session, owner, identifier))

    def claim(self, owner, identifier, body):
        decision = body.model_dump(mode='json', exclude={'expected_revision'})
        with self.transactions.write(owner) as tx:
            session, now = tx._session, self.clock()
            row = self._get(session, owner, identifier)
            payload = row['payload']
            if body.decision == 'approve' and payload['action'] in ('create', 'edit'):
                details = body.details or EventDraft.model_validate(payload['candidate'])
                self.events._values(details)
                decision['details'] = details.model_dump(mode='json')
            if row['state'] in ('approved', 'dismissed'):
                if row['decision'] != decision: raise conflict()
                return dict(terminal=True, proposal=self._public(row))
            if row['state'] not in ('pending', 'deciding') or row['expires_at'] <= now:
                raise AppError('PROPOSAL_EXPIRED', 'This proposal has expired or was cancelled.', 409)
            self._source(session, owner, row)
            if row['decision'] is not None and row['decision'] != decision: raise conflict()
            if row['claim_until'] and row['claim_until'] > now:
                raise AppError('PROPOSAL_BUSY', 'This decision is being saved. Retry shortly.', 409)
            if row['decision'] is None and row['revision'] != body.expected_revision: raise conflict()
            claim = str(uuid4())
            session.execute(update(p).where(p.c.id == identifier).values(state='deciding', decision=decision,
                claim_id=claim, claim_until=now+timedelta(seconds=30), revision=row['revision']+1))
            return dict(terminal=False, claim_id=claim, decision=decision, proposal_id=identifier)

    def commit(self, owner, identifier, claim, *, automatic=False):
        with self.transactions.write(owner) as tx:
            session = tx._session
            row = self._get(session, owner, identifier)
            if row['claim_id'] != claim or row['claim_until'] <= self.clock() or row['state'] != 'deciding':
                raise AppError('PROPOSAL_CLAIM_EXPIRED', 'This decision needs to be retried.', 409)
            source = self._source(session, owner, row)
            if automatic:
                if not self.events._preferences(session,owner)['automatic_events']:
                    raise AppError('EVENT_CAPTURE_DISABLED','Automatic capture is disabled.',409)
                turn=session.execute(select(turns).where(turns.c.learner_id==owner,turns.c.id==row['turn_id'])).mappings().first()
                if not turn or turn['state']!='RUNNING' or turn['attempt']!=row['attempt'] or turn['lease_until']<=self.clock():
                    raise AppError('CHAT_ATTEMPT_EXPIRED','This generation is no longer active.',409)
            decision, payload = row['decision'], row['payload']
            event_id = None
            if decision['decision'] == 'approve':
                if payload['action'] == 'create':
                    body = EventCreate(**decision['details'], client_request_id=identifier)
                    outcome = self.events.create_in_transaction(tx, body)
                    event_id = str(outcome['event_id'])
                    session.execute(update(events).where(events.c.learner_id == owner, events.c.id == event_id).values(origin='ai'))
                else:
                    body = EventEdit(expected_revision=payload['target_revision'], client_request_id=identifier,
                        details=decision.get('details') if payload['action'] == 'edit' else None,
                        status=payload['status'] if payload['action'] == 'status' else None)
                    outcome = self.events.edit_in_transaction(tx, payload['target_id'], body)
                    event_id = str(outcome['event_id'])
                session.execute(evidence.insert().values(id=str(uuid4()), learner_id=owner, event_id=event_id,
                    quote=row['quote'], source_date=source['created_at'], source_timezone=decision.get('details', {}).get('timezone') or 'UTC',
                    source_deleted=False, conversation_id=source['conversation_id'], message_id=source['id'], policy_version='event-admission-v1'))
            session.execute(update(p).where(p.c.id == identifier).values(state='approved' if event_id else 'dismissed',
                event_id=event_id, revision=row['revision']+1, claim_id=None, claim_until=None))
            delete_thread(session, thread_id(owner, identifier))
            return self._public(self._get(session, owner, identifier))

    def release(self,owner,identifier):
        with self.transactions.write(owner) as tx:
            row=self._get(tx._session,owner,identifier)
            if row['state']=='deciding':
                tx._session.execute(update(p).where(p.c.id==identifier).values(state='pending',decision=None,claim_id=None,claim_until=None,revision=row['revision']+1))
                delete_thread(tx._session,thread_id(owner,identifier))

    @staticmethod
    def detach_chat(session, owner, conversation_id):
        identifiers = list(session.execute(select(p.c.id).where(p.c.learner_id == owner, p.c.conversation_id == conversation_id)).scalars())
        for identifier in identifiers: delete_thread(session, thread_id(owner, identifier))
        session.execute(delete(p).where(p.c.learner_id == owner, p.c.conversation_id == conversation_id))
