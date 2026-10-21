"""Atomic change capture, owner-first leases, and safe bounded context reads."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from app.summarization.execution import MAX_ATTEMPTS, LEASE_SECONDS, retry_delay
from sqlalchemy import select, update, delete, func, or_, tuple_
from sqlalchemy.dialects.postgresql import insert
from app.db.owner_transactions import lock_owner
from .tables import memories as m, summary_state as s, summary_changes as c, summary_jobs as j
from app.core.read_cache import ReadCache
from app.core.config import settings

_contexts = ReadCache(capacity=128, ttl=None)
from app.history_management.memory.summary_schemas import bounded, envelope, MemorySummary, fits


def now():
    return datetime.now(timezone.utc)


def projection(row):
    if not row or row['status'] != 'active' or row.get('expires_at') and row['expires_at'] <= now():
        return None
    return dict(id=str(row['id']), revision=row['revision'], content=row['content'], category=row['category'],
                pinned=row['pinned'], expires_at=row['expires_at'].isoformat() if row.get('expires_at') else None)


def eligible():
    return (m.c.status == 'active', or_(m.c.expires_at.is_(None), m.c.expires_at > now()))


def queue(session, owner, *, rebuild=False):
    stamp = now()
    statement = insert(j).values(learner_id=owner, available_at=stamp+timedelta(seconds=1), queued_at=stamp, rebuild=rebuild)
    session.execute(statement.on_conflict_do_update(index_elements=[j.c.learner_id], set_=dict(
        available_at=func.least(stamp+timedelta(seconds=1), j.c.queued_at+timedelta(seconds=5)),
        failed=False, error_code=None, attempts=0, rebuild=j.c.rebuild | rebuild)))


def ensure(session, owner):
    row = session.execute(select(s).where(s.c.learner_id == owner)).mappings().first()
    if row:
        return dict(row)
    return dict(session.execute(insert(s).values(learner_id=owner).returning(s)).mappings().one())


def valid_blocks(value):
    try:
        blocks = MemorySummary(blocks=value).model_dump(mode='json')['blocks']
        return blocks if fits(blocks) else None
    except (ValueError, TypeError):
        return None


def capture(session, owner, before, after):
    """Called within the canonical mutation's owner-locked transaction."""
    old, new = projection(before), projection(after)
    if not old and not new and not (before and before['status'] == 'active'):
        return
    state = ensure(session, owner)
    checked_blocks = valid_blocks(state['blocks'])
    corrupt = checked_blocks is None
    state['blocks'] = checked_blocks or []
    identifier = str((after or before)['id'])
    # Revision-only evidence bookkeeping does not require a paid model call.
    if not corrupt and old and new and {k:v for k,v in old.items() if k != 'revision'} == {k:v for k,v in new.items() if k != 'revision'}:
        blocks = state['blocks']
        for block in blocks:
            for support in block['supports']:
                if support['id'] == identifier:
                    support['revision'] = new['revision']
        session.execute(update(s).where(s.c.learner_id == owner).values(blocks=blocks, summary_revision=s.c.summary_revision+1))
        session.execute(update(c).where(c.c.learner_id == owner, c.c.memory_id == identifier, c.c.after.is_not(None)).values(after=new))
        session.execute(update(j).where(j.c.learner_id == owner).values(checkpoint={}))
        return
    revision = state['source_revision']+1
    # Invalidate stored prose immediately. Recover the unaffected facts from any
    # mixed block through targeted canonical projections in subsequent jobs.
    blocks, survivors = [], set()
    for block in state['blocks']:
        if any(x['id'] == identifier for x in block['supports']):
            survivors.update(x['id'] for x in block['supports'] if x['id'] != identifier)
        else:
            blocks.append(block)
    # Scrub all historical delta copies of this fact, including forgotten text.
    session.execute(delete(c).where(c.c.learner_id == owner, c.c.memory_id == identifier))
    session.execute(c.insert().values(learner_id=owner, source_revision=revision, memory_id=identifier, after=new))
    for row in session.execute(select(m).where(m.c.learner_id == owner, m.c.id.in_(survivors), *eligible())).mappings():
        revision += 1
        session.execute(c.insert().values(learner_id=owner, source_revision=revision, memory_id=row['id'], after=projection(row)))
    totals = session.execute(select(func.min(m.c.expires_at).label('expiry'), func.count().label('count')).where(m.c.learner_id == owner, *eligible())).mappings().one()
    expiry = totals['expiry']
    session.execute(update(s).where(s.c.learner_id == owner).values(source_revision=revision, blocks=blocks, next_expiry_at=expiry))
    # Remove personal text from any in-progress reconciliation checkpoint too.
    session.execute(update(j).where(j.c.learner_id == owner).values(checkpoint={}))
    if not totals['count']:
        session.execute(update(s).where(s.c.learner_id == owner).values(blocks=[], published_source_revision=revision,
                       summary_revision=s.c.summary_revision+1, next_expiry_at=None))
        session.execute(delete(c).where(c.c.learner_id == owner))
        session.execute(delete(j).where(j.c.learner_id == owner))
    else:
        queue(session, owner, rebuild=corrupt or new is None)


class MemorySummaryRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def context(self, owner):
        """Unchanged summaries need one freshness SELECT, without an owner lock."""
        from app.langchain.prompts.memory_summary import VERSION
        key = (self.sessions, owner, VERSION, settings.memory_summary_max_tokens, settings.memory_summary_max_characters)
        cached = _contexts.get(key)
        with self.sessions() as session:
            if cached is not None:
                value, fence = cached
                ids = {x['id']: x['revision'] for x in fence['supports']}
                valid_count = select(func.count()).select_from(m).where(m.c.learner_id == owner,
                    tuple_(m.c.id, m.c.revision).in_(list(ids.items())), *eligible()).scalar_subquery()
                state = session.execute(select(s.c.source_revision, s.c.published_source_revision,
                    s.c.summary_revision, s.c.prompt_version, s.c.next_expiry_at, s.c.reconciled_at,
                    valid_count.label('valid_count')).where(s.c.learner_id == owner)).mappings().first()
                if (self._ready(state, VERSION) and state['source_revision'] == fence['source_revision']
                        and state['summary_revision'] == value['revision'] and state['valid_count'] == len(ids)
                        and (not fence['expires_at'] or datetime.fromisoformat(fence['expires_at']) > now())):
                    return value, fence
        # Cold reads use a consistent snapshot, not the owner write boundary.
        with self.sessions() as session:
            session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
            state = session.execute(select(s).where(s.c.learner_id == owner)).mappings().first()
            if self._ready(state, VERSION):
                blocks = valid_blocks(state['blocks'])
                if blocks is not None:
                    supports = [x for block in blocks for x in block['supports']]
                    ids = {x['id']: x['revision'] for x in supports}
                    rows = {str(row['id']): row for row in session.execute(select(m.c.id, m.c.revision,
                        m.c.pinned, m.c.expires_at).where(m.c.learner_id == owner, m.c.id.in_(ids), *eligible())).mappings()}
                    if all(identifier in rows and rows[identifier]['revision'] == revision for identifier, revision in ids.items()):
                        blocks.sort(key=lambda block: not any(rows[x['id']]['pinned'] for x in block['supports']))
                        blocks = bounded(blocks)
                        supports = [x for block in blocks for x in block['supports']]
                        expiry = min((rows[x['id']]['expires_at'] for x in supports if rows[x['id']]['expires_at']), default=None)
                        value = envelope(blocks, 'ready' if blocks else 'empty', state['summary_revision'])
                        fence = dict(source_revision=state['source_revision'], supports=supports,
                                     expires_at=expiry.isoformat() if expiry else None)
                        _contexts.put(key, (value, fence))
                        return value, fence
        return self._context_locked(owner)

    @staticmethod
    def _ready(state, version):
        return (state is not None and state['source_revision'] == state['published_source_revision']
            and (not state['next_expiry_at'] or state['next_expiry_at'] > now())
            and (not state['source_revision'] or state['prompt_version'] == version
                 and (not state['reconciled_at'] or state['reconciled_at'] >= now()-timedelta(days=30))))

    def _context_locked(self, owner):
        from app.langchain.prompts.memory_summary import VERSION
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            state = ensure(session, owner)
            checked_blocks = valid_blocks(state['blocks'])
            if checked_blocks is None:
                state.update(blocks=[], source_revision=state['source_revision']+1)
                session.execute(update(s).where(s.c.learner_id == owner).values(blocks=[], source_revision=state['source_revision']))
                queue(session, owner, rebuild=True)
            else:
                state['blocks'] = checked_blocks
            ids = {x['id'] for b in state['blocks'] for x in b['supports']}
            rows = {str(r['id']): dict(r) for r in session.execute(select(m).where(m.c.learner_id == owner, m.c.id.in_(ids), *eligible())).mappings()}
            blocks = [b for b in state['blocks'] if all(x['id'] in rows and rows[x['id']]['revision'] == x['revision'] for x in b['supports'])]
            dirty = state['source_revision'] != state['published_source_revision']
            pinned_ids = {identifier for identifier, row in rows.items() if row['pinned']}
            if dirty:
                changes = list(session.execute(select(c).where(c.c.learner_id == owner,
                    c.c.source_revision > state['published_source_revision']).order_by(c.c.source_revision.desc()).limit(64)).mappings())
                changed_ids = {str(x['memory_id']) for x in changes if x['after']}
                fresh = list(session.execute(select(m).where(m.c.learner_id == owner, m.c.id.in_(changed_ids), *eligible())
                    .order_by(m.c.pinned.desc(), m.c.updated_at.desc())).mappings())
                covered = {x['id'] for b in blocks for x in b['supports']}
                additions = [dict(text=r['content'], supports=[dict(id=str(r['id']), revision=r['revision'])]) for r in fresh if str(r['id']) not in covered]
                pinned_ids.update(str(r['id']) for r in fresh if r['pinned'])
                blocks = [*additions, *blocks]
            blocks.sort(key=lambda block: not any(x['id'] in pinned_ids for x in block['supports']))
            blocks = bounded(blocks)
            expiry = min((rows[x['id']]['expires_at'] for b in blocks for x in b['supports']
                          if x['id'] in rows and rows[x['id']]['expires_at']), default=None)
            supports = [x for b in blocks for x in b['supports']]
            # New fallback facts can have expirations too; fence all supplied IDs.
            if supports:
                expiry = session.scalar(select(func.min(m.c.expires_at)).where(m.c.learner_id == owner, m.c.id.in_([x['id'] for x in supports])))
            expired = bool(state['next_expiry_at'] and state['next_expiry_at'] <= now())
            if expired:
                queue(session, owner, rebuild=True)
            if state['source_revision'] and (state['prompt_version'] != VERSION or state['reconciled_at'] and state['reconciled_at'] < now()-timedelta(days=30)) and not session.scalar(select(j.c.learner_id).where(j.c.learner_id == owner)):
                queue(session, owner, rebuild=True)
            status = 'updating' if dirty or expired else 'ready' if blocks else 'empty'
            return envelope(blocks, status, state['summary_revision']), dict(source_revision=state['source_revision'], supports=supports,
                expires_at=expiry.isoformat() if expiry else None)

    @staticmethod
    def current(session, owner, fence):
        if not fence:
            return True
        if fence.get('expires_at') and datetime.fromisoformat(fence['expires_at']) <= now():
            return False
        ids = {x['id']: x['revision'] for x in fence.get('supports', [])}
        count = select(func.count()).select_from(m).where(m.c.learner_id == owner,
            tuple_(m.c.id, m.c.revision).in_(list(ids.items())), *eligible()).scalar_subquery()
        row = session.execute(select(s.c.source_revision, count.label('valid_supports')).where(s.c.learner_id == owner)).first()
        return (row.source_revision if row else 0) == fence['source_revision'] and (row.valid_supports if row else 0) == len(ids)

    def fence_current(self, owner, fence):
        # One statement/snapshot: stream monitoring takes no owner write lock.
        with self.sessions() as session:
            return self.current(session, owner, fence)

    def claim(self):
        from app.chat.repositories.tables import sync_state
        with self.sessions.begin() as session:
            owners = list(session.scalars(select(j.c.learner_id).where(j.c.failed.is_(False), j.c.available_at <= now(),
                or_(j.c.lease_until.is_(None), j.c.lease_until < now())).order_by(j.c.available_at).limit(16)))
            for owner in owners:
                # Owner before job lock: same order as saves/deletions/completion.
                session.execute(insert(sync_state).values(learner_id=owner, revision=0, floor=0).on_conflict_do_nothing())
                if not session.execute(select(sync_state).where(sync_state.c.learner_id == owner).with_for_update(skip_locked=True)).first():
                    continue
                job = session.execute(select(j).where(j.c.learner_id == owner, j.c.failed.is_(False), j.c.available_at <= now(),
                    or_(j.c.lease_until.is_(None), j.c.lease_until < now())).with_for_update(skip_locked=True)).mappings().first()
                if not job:
                    continue
                state = ensure(session, owner)
                token = str(uuid4())
                session.execute(update(j).where(j.c.learner_id == owner).values(lease_token=token, lease_until=now()+timedelta(seconds=LEASE_SECONDS)))
                return dict(job, token=token, state=state)

    def packet(self, claim, limit=12):
        from app.langchain.prompts.memory_summary import VERSION
        owner, state = claim['learner_id'], claim['state']
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            live = ensure(session, owner)
            if live['source_revision'] != state['source_revision']:
                return None
            rebuild = claim['rebuild'] or state['prompt_version'] != VERSION or state['source_revision']-state['reconciled_revision'] >= 100 or (
                state['reconciled_at'] and state['reconciled_at'] < now()-timedelta(days=30))
            checked_blocks = valid_blocks(state['blocks'])
            rebuild = rebuild or checked_blocks is None
            if not rebuild and state['source_revision'] > state['published_source_revision'] and not session.scalar(
                    select(c.c.source_revision).where(c.c.learner_id == owner, c.c.source_revision > state['published_source_revision']).limit(1)):
                rebuild = True
            checkpoint = claim['checkpoint'] if rebuild else {}
            if (not isinstance(checkpoint, dict) or checkpoint.get('source_revision') != state['source_revision']
                    or checkpoint.get('prompt_version') != VERSION):
                checkpoint = {}
            checkpoint_blocks = valid_blocks(checkpoint.get('blocks', []))
            try:
                if checkpoint.get('cursor'):
                    from uuid import UUID
                    UUID(checkpoint['cursor'])
            except (ValueError, TypeError, AttributeError):
                checkpoint = {}
                checkpoint_blocks = []
            if checkpoint_blocks is None:
                checkpoint = {}
            previous = (checkpoint_blocks or []) if rebuild else checked_blocks
            support_ids = {x['id'] for b in previous for x in b['supports']}
            pinned = list(session.scalars(select(m.c.id).where(m.c.learner_id == owner, m.c.id.in_(support_ids), m.c.pinned.is_(True), *eligible())))
            if rebuild:
                query = select(m).where(m.c.learner_id == owner, *eligible())
                if checkpoint.get('cursor'):
                    query = query.where(m.c.id > checkpoint['cursor'])
                records = list(session.execute(query.order_by(m.c.id).limit(limit+1)).mappings())
                facts = [projection(x) for x in records[:limit]]
                return dict(previous_summary=previous, changes=facts, removed=[], pinned_supports=[str(x) for x in pinned], rebuild=True,
                    through=state['source_revision'], more=len(records)>limit, cursor=str(records[limit-1]['id']) if len(records)>limit else None)
            changes = list(session.execute(select(c).where(c.c.learner_id == owner, c.c.source_revision > state['published_source_revision'])
                .order_by(c.c.source_revision).limit(limit+1)).mappings())
            facts = [x['after'] for x in changes[:limit] if x['after']]
            return dict(previous_summary=state['blocks'], changes=facts,
                pinned_supports=[str(x) for x in pinned],
                removed=[str(x['memory_id']) for x in changes[:limit] if not x['after']], rebuild=False,
                through=changes[min(limit,len(changes))-1]['source_revision'] if changes else state['source_revision'], more=len(changes)>limit)

    def publish(self, claim, packet, blocks):
        from app.langchain.prompts.memory_summary import VERSION
        owner = claim['learner_id']
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            job = session.execute(select(j).where(j.c.learner_id == owner, j.c.lease_token == claim['token'], j.c.lease_until > now())).mappings().first()
            if not job:
                return False
            state = ensure(session, owner)
            if state['source_revision'] != claim['state']['source_revision'] or state['summary_revision'] != claim['state']['summary_revision']:
                session.execute(update(j).where(j.c.learner_id == owner).values(lease_token=None, lease_until=None, available_at=now(), checkpoint={}))
                return False
            supports = [x for b in blocks for x in b['supports']]
            if not self.current(session, owner, dict(source_revision=state['source_revision'], supports=supports)):
                raise ValueError('Summary supports changed')
            if packet['rebuild'] and packet['more']:
                session.execute(update(j).where(j.c.learner_id == owner).values(checkpoint=dict(blocks=blocks,
                    cursor=packet['cursor'], source_revision=state['source_revision'], prompt_version=VERSION), rebuild=True,
                    lease_token=None, lease_until=None, attempts=0, available_at=now()))
                return True
            values = dict(blocks=blocks, published_source_revision=packet['through'], summary_revision=state['summary_revision']+1,
                prompt_version=VERSION, updated_at=now(), next_expiry_at=session.scalar(select(func.min(m.c.expires_at)).where(m.c.learner_id == owner, *eligible())))
            if packet['rebuild']:
                values.update(reconciled_at=now(), reconciled_revision=state['source_revision'])
            session.execute(update(s).where(s.c.learner_id == owner).values(**values))
            session.execute(delete(c).where(c.c.learner_id == owner, c.c.source_revision <= packet['through']))
            if packet['more']:
                session.execute(update(j).where(j.c.learner_id == owner).values(lease_token=None, lease_until=None, attempts=0, available_at=now(), checkpoint={}))
            else:
                session.execute(delete(j).where(j.c.learner_id == owner))
            return True

    def release(self, claim, error=None):
        with self.sessions.begin() as session:
            lock_owner(session, claim['learner_id'])
            state = ensure(session, claim['learner_id'])
            stale = state['source_revision'] != claim['state']['source_revision'] or state['summary_revision'] != claim['state']['summary_revision']
            attempts = claim['attempts']+1 if error and not stale else 0
            session.execute(update(j).where(j.c.learner_id == claim['learner_id'], j.c.lease_token == claim['token']).values(
                lease_token=None, lease_until=None, attempts=attempts, failed=attempts >= MAX_ATTEMPTS,
                error_code=type(error).__name__ if error else None,
                available_at=now()+timedelta(seconds=retry_delay(attempts) if error else 0)))

    def sweep(self):
        with self.sessions() as session:
            owners = list(session.scalars(select(s.c.learner_id).where(s.c.next_expiry_at <= now()).order_by(s.c.next_expiry_at).limit(10)))
        for owner in owners:
            with self.sessions.begin() as session:
                lock_owner(session, owner)
                state = ensure(session, owner)
                if state['next_expiry_at'] and state['next_expiry_at'] <= now():
                    session.execute(update(s).where(s.c.learner_id == owner).values(source_revision=s.c.source_revision+1,
                        next_expiry_at=session.scalar(select(func.min(m.c.expires_at)).where(m.c.learner_id == owner, *eligible()))))
                    queue(session, owner, rebuild=True)

    def retry(self, owner):
        with self.sessions.begin() as session:
            lock_owner(session, owner)
            ensure(session, owner)
            queue(session, owner, rebuild=True)

    def diagnostics(self):
        with self.sessions() as session:
            return dict(session.execute(select(func.count().label('pending'), func.count().filter(j.c.failed).label('failed'),
                func.min(j.c.queued_at).label('oldest_queued_at'))).mappings().one())
