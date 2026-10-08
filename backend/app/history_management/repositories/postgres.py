"""Short, owner-serialized transactions. No provider calls under database locks."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from uuid import uuid4, UUID
from sqlalchemy import select, update, delete, func, or_, and_
from sqlalchemy.dialects.postgresql import insert
from app.core.exceptions import AppError
from app.db.owner_transactions import lock_owner
from app.chat.repositories.tables import turns
from .tables import memories as m, evidence as e, revisions as r, preferences as p, suppression as s, receipts as rc


def now():
    return datetime.now(timezone.utc)


def fingerprint(value):
    return sha256(re.sub(r'\s+', ' ', value.casefold()).strip().encode()).hexdigest()


def source_fingerprint(message_id):
    return fingerprint('source:' + str(message_id))


def conflict():
    return AppError('MEMORY_CONFLICT', 'This memory changed. Reload it before saving your draft.', 409)


class MemoryRepository:
    def __init__(self, sessions, active_limit=200, pending_limit=50):
        self.sessions = sessions
        self.active_limit, self.pending_limit = active_limit, pending_limit

    def _lock(self, session, owner):
        lock_owner(session, owner)
        session.execute(insert(p).values(learner_id=owner, automatic_memory=True, revision=1).on_conflict_do_nothing())
        return dict(session.execute(select(p).where(p.c.learner_id == owner)).mappings().one())

    def preferences(self, owner):
        with self.sessions() as session:
            row = session.execute(select(p).where(p.c.learner_id == owner)).mappings().first()
            result = dict(row) if row else dict(automatic_memory=True, revision=0)
            result.pop('learner_id', None)
            return dict(result, active_limit=self.active_limit, pending_limit=self.pending_limit, manual_limit=1000)

    def set_preferences(self, owner, body):
        with self.sessions.begin() as session:
            existing = session.execute(select(p).where(p.c.learner_id == owner)).mappings().first()
            current = existing['revision'] if existing else 0
            self._lock(session, owner)
            # Re-read after locking: another writer may have committed meanwhile.
            row = session.execute(select(p).where(p.c.learner_id == owner)).mappings().one()
            expected = body.expected_revision
            if row['revision'] != expected and not (current == 0 and expected == 0 and row['revision'] == 1):
                raise conflict()
            revision = row['revision'] + 1
            session.execute(update(p).where(p.c.learner_id == owner).values(automatic_memory=body.automatic_memory, revision=revision))
            return dict(automatic_memory=body.automatic_memory, revision=revision, active_limit=self.active_limit, pending_limit=self.pending_limit, manual_limit=1000)

    def _get(self, session, owner, identifier):
        row = session.execute(select(m).where(m.c.learner_id == owner, m.c.id == identifier)).mappings().first()
        if not row:
            raise AppError('MEMORY_NOT_FOUND', 'Memory not found.', 404)
        return dict(row)

    def detail(self, owner, identifier):
        with self.sessions() as session:
            row = self._get(session, owner, identifier)
            # A predecessor can be edited/pinned after a conflict was proposed.
            # Show current statements; explicit resolution fences these versions.
            if row['conflicts']:
                ids = [x['memory_id'] for x in row['conflicts']]
                live = {x['id']: x for x in session.execute(select(m.c.id, m.c.content, m.c.revision)
                    .where(m.c.learner_id == owner, m.c.id.in_(ids))).mappings()}
                row['conflicts'] = [dict(memory_id=key, content=live[key]['content'], revision=live[key]['revision'])
                    for key in ids if key in live]
            row['evidence'] = [dict(x) for x in session.execute(select(e).where(e.c.learner_id == owner, e.c.memory_id == identifier).order_by(e.c.source_date.desc()).limit(5)).mappings()]
            return self._public(row)

    def receipt(self, owner, operation):
        with self.sessions() as session:
            row = session.execute(select(rc).where(rc.c.learner_id == owner, rc.c.operation_key == operation)).mappings().first()
            if not row:
                return None
            live = session.execute(select(m).where(m.c.learner_id == owner, m.c.id == row['memory_id'])).mappings().first() if row['memory_id'] else None
            return dict(outcome=row['outcome'] if live else 'rejected', memory=self._public(live) if live else None)

    @staticmethod
    def _public(row):
        value = dict(row)
        value.pop('learner_id', None)
        value.pop('fingerprint', None)
        value['stale'] = bool(value.get('expires_at') and value['expires_at'] <= now())
        for item in value.get('evidence', []):
            item.pop('learner_id', None)
        return value

    def list(self, owner, query='', status=None, cursor=None, limit=30, recall=False):
        with self.sessions() as session:
            stmt = select(m).where(m.c.learner_id == owner)
            if status:
                stmt = stmt.where(m.c.status == status)
            if recall:
                stmt = stmt.where(m.c.status == 'active', or_(m.c.expires_at.is_(None), m.c.expires_at > now()))
            if query:
                vector = func.to_tsvector('simple', m.c.content)
                words = func.websearch_to_tsquery('simple', query)
                # Trigram-indexed fallback covers inflections/code identifiers.
                escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                stmt = stmt.where(or_(vector.op('@@')(words), m.c.content.ilike('%' + escaped + '%', escape='\\')))
            if cursor:
                try:
                    stamp, identifier = json.loads(cursor)
                    stamp = datetime.fromisoformat(stamp)
                    identifier = str(UUID(identifier))
                    if not stamp.tzinfo:
                        raise ValueError()
                    stmt = stmt.where(or_(m.c.updated_at < stamp, and_(m.c.updated_at == stamp, m.c.id < identifier)))
                except (ValueError, TypeError):
                    raise AppError('MEMORY_CURSOR_INVALID', 'Invalid memory cursor.', 422)
            order = [m.c.updated_at.desc(), m.c.id.desc()]
            if recall and query:
                order = [func.ts_rank_cd(func.to_tsvector('simple', m.c.content), func.websearch_to_tsquery('simple', query)).desc(), *order]
            rows = [dict(x) for x in session.execute(stmt.order_by(*order).limit(min(limit, 50) + 1)).mappings()]
            more = len(rows) > limit
            rows = rows[:limit]
            return dict(items=[self._public(x) for x in rows], next_cursor=json.dumps([rows[-1]['updated_at'].isoformat(), rows[-1]['id']]) if more else None)

    def related(self, owner, content, known_ids=()):
        stop = {'i','a','an','the','is','am','are','my','me','that','this','remember','now','actually','please','to','of','in','for','and','user','users','has','have','with'}
        terms = [x for x in dict.fromkeys(re.findall(r'\w+', content.casefold())) if x not in stop][:12]
        with self.sessions() as session:
            base = select(m).where(m.c.learner_id == owner, m.c.status == 'active',
                or_(m.c.expires_at.is_(None), m.c.expires_at > now()))
            if terms:
                words = func.websearch_to_tsquery('simple', ' OR '.join('"'+x+'"' for x in terms))
                vector = func.to_tsvector('simple', m.c.content)
                base = base.where(or_(vector.op('@@')(words), m.c.id.in_(known_ids)))
                base = base.order_by(func.ts_rank_cd(vector, words).desc(), m.c.updated_at.desc())
            elif known_ids:
                base = base.where(m.c.id.in_(known_ids)).order_by(m.c.updated_at.desc())
            else:
                return []
            return [dict(x) for x in session.execute(base.limit(5)).mappings()]

    def _revision(self, session, owner, identifier, revision, actor):
        session.execute(r.insert().values(learner_id=owner, memory_id=identifier, revision=revision, actor=actor, created_at=now()))

    def _receipt(self, session, owner, operation, outcome, identifier=None, scope=None, request_hash=None):
        session.execute(rc.insert().values(learner_id=owner, operation_key=operation, outcome=outcome,
            memory_id=identifier, turn_id=scope['turn_id'] if scope else None,
            request_hash=request_hash or operation,
            conversation_id=scope['conversation_id'] if scope else None, created_at=now()))

    def _fence(self, session, owner, scope):
        if scope:
            row = session.execute(select(turns).where(turns.c.id == scope['turn_id'], turns.c.learner_id == owner)).mappings().first()
            if not row or row['attempt'] != scope['attempt'] or row['state'] != 'RUNNING' or row['lease_until'] <= now():
                raise AppError('MEMORY_TURN_EXPIRED', 'This generation is no longer active.', 409)

    def write(self, owner, content, category, operation, *, origin='manual', status='active', evidence=None,
              scope=None, memory_id=None, expected_revision=None, pinned=False, expires_at=None, conflict_ids=()):
        from app.history_management.memory.validation import SECRET
        if SECRET.search(content):
            raise AppError('MEMORY_SECRET', 'Do not store passwords, credentials or secrets in memory.', 422)
        request_hash = sha256(json.dumps([content, category, pinned, expires_at.isoformat() if expires_at else None], ensure_ascii=False).encode()).hexdigest()
        with self.sessions.begin() as session:
            prefs = self._lock(session, owner)
            self._fence(session, owner, scope)
            previous = session.execute(select(rc).where(rc.c.learner_id == owner, rc.c.operation_key == operation)).mappings().first()
            if previous:
                if origin == 'manual' and previous['request_hash'] != request_hash:
                    raise AppError('MEMORY_IDEMPOTENCY_CONFLICT', 'This save identifier was used for different content.', 409)
                if not previous['memory_id']:
                    return dict(outcome=previous['outcome'])
                live = session.execute(select(m).where(m.c.learner_id == owner, m.c.id == previous['memory_id'])).mappings().first()
                if live and origin == 'ai' and live['fingerprint'] != fingerprint(content):
                    return dict(outcome='rejected', reason='That saved statement was corrected. The previous save result is no longer current.')
                return dict(outcome=previous['outcome'] if live else 'rejected', memory=self._public(live) if live else None)
            if origin == 'ai' and not prefs['automatic_memory']:
                return dict(outcome='rejected', reason='Automatic memory is disabled.')
            claim_hash = fingerprint(content)
            blocked = [claim_hash]
            if evidence and evidence.get('message_id'):
                blocked.append(source_fingerprint(evidence['message_id']))
                # Resolve again under the shared lock; a chat deletion may have
                # happened while semantic verification was in flight.
                from app.chat.repositories.tables import messages
                live = session.execute(select(messages.c.id).where(messages.c.learner_id == owner,
                    messages.c.id == evidence['message_id'], messages.c.role == 'user')).first()
                if not live:
                    return dict(outcome='rejected', reason='Source message was deleted.')
            if origin == 'ai' and session.execute(select(s).where(s.c.learner_id == owner, s.c.fingerprint.in_(blocked))).first():
                return dict(outcome='rejected', reason='This claim or source is blocked from automatic saving. Manage memories explicitly in Settings.')
            duplicate = session.execute(select(m).where(m.c.learner_id == owner, m.c.fingerprint == claim_hash)).mappings().first()
            if duplicate and str(duplicate['id']) != str(memory_id):
                if origin == 'manual':
                    if duplicate['status'] == 'conflict':
                        raise AppError('MEMORY_CONFLICT_REVIEW', 'That statement has conflicting memories. Review and resolve it in Settings.', 409)
                    # Typing a matching candidate is an explicit user assertion,
                    # not an AI-driven promotion. Reaffirm freshness and provenance.
                    stamp = now()
                    values = dict(status='active', origin='manual', category=category,
                        confirmed_at=stamp, updated_at=stamp, expires_at=expires_at,
                        pinned=duplicate['pinned'] or pinned, revision=duplicate['revision'] + 1)
                    session.execute(update(m).where(m.c.learner_id == owner, m.c.id == duplicate['id']).values(**values))
                    for source in session.scalars(select(e.c.message_id).where(e.c.learner_id == owner,
                            e.c.memory_id == duplicate['id'], e.c.message_id.is_not(None))):
                        session.execute(insert(s).values(learner_id=owner, fingerprint=source_fingerprint(source), created_at=stamp).on_conflict_do_nothing())
                    session.execute(delete(e).where(e.c.learner_id == owner, e.c.memory_id == duplicate['id']))
                    session.execute(e.insert().values(id=str(uuid4()), learner_id=owner, memory_id=duplicate['id'],
                        quote=content, source_date=stamp, source_deleted=False, explicit_consent=True))
                    self._revision(session, owner, duplicate['id'], values['revision'], 'manual')
                    self._receipt(session, owner, operation, 'saved', duplicate['id'], scope, request_hash)
                    return dict(outcome='saved', memory=self._public(dict(duplicate, **values)))
                if evidence and status == 'active' and not session.execute(select(e.c.id).where(e.c.learner_id == owner, e.c.memory_id == duplicate['id'], e.c.message_id == evidence['message_id'])).first():
                    # New explicit support may strengthen a candidate's evidence,
                    # but never silently promotes it. Keep at most five quotes.
                    previous_evidence = list(session.scalars(select(e.c.id).where(e.c.learner_id == owner, e.c.memory_id == duplicate['id']).order_by(e.c.source_date.desc())))
                    if len(previous_evidence) >= 5:
                        # Preserve non-plaintext source suppression before
                        # discarding a quote, so forgetting cannot later be
                        # bypassed by rewording an older supporting source.
                        retired_sources = session.scalars(select(e.c.message_id).where(e.c.learner_id == owner,
                            e.c.id.in_(previous_evidence[4:]), e.c.message_id.is_not(None)))
                        for source in retired_sources:
                            session.execute(insert(s).values(learner_id=owner, fingerprint=source_fingerprint(source), created_at=now()).on_conflict_do_nothing())
                        session.execute(delete(e).where(e.c.learner_id == owner, e.c.id.in_(previous_evidence[4:])))
                    session.execute(e.insert().values(id=str(uuid4()), learner_id=owner, memory_id=duplicate['id'], **evidence))
                    values = dict(revision=duplicate['revision']+1, updated_at=now())
                    if duplicate['origin'] == 'ai' and duplicate['status'] == 'active' and expires_at is not None:
                        values.update(expires_at=expires_at, confirmed_at=evidence['source_date'])
                    session.execute(update(m).where(m.c.learner_id == owner, m.c.id == duplicate['id']).values(**values))
                    self._revision(session, owner, duplicate['id'], duplicate['revision']+1, origin)
                    duplicate = dict(duplicate, **values)
                self._receipt(session, owner, operation, 'already_known', duplicate['id'], scope, request_hash)
                return dict(outcome='already_known', memory=self._public(duplicate))
            stamp = now()
            conflicts = []
            if status == 'conflict':
                conflicts = [dict(memory_id=x['id'], revision=x['revision'], content=x['content']) for x in session.execute(select(m).where(m.c.learner_id == owner, m.c.id.in_(conflict_ids), m.c.status == 'active')).mappings()]
                if not conflicts:
                    return dict(outcome='conflict', reason='The conflicting records changed. Review them in Settings.')
            if memory_id:
                current = self._get(session, owner, memory_id)
                if current['revision'] != expected_revision:
                    raise conflict()
                if origin == 'ai' and current['origin'] == 'manual':
                    return dict(outcome='conflict', reason='A manual memory must be edited by its user.')
                # AI may propose corrections, but must not silently supersede an
                # independently saved fact or promote an inferred candidate.
                if origin == 'ai':
                    return dict(outcome='conflict', reason='Confirm this correction in Settings.')
                revision = current['revision'] + 1
                session.execute(update(m).where(m.c.id == memory_id, m.c.learner_id == owner).values(content=content,
                    fingerprint=claim_hash, category=category, status=status, origin=origin, revision=revision,
                    updated_at=stamp, confirmed_at=stamp, pinned=pinned, expires_at=expires_at))
                session.execute(delete(e).where(e.c.learner_id == owner, e.c.memory_id == memory_id))
                identifier = memory_id
            else:
                count = session.scalar(select(func.count()).select_from(m).where(m.c.learner_id == owner,
                    m.c.origin == 'ai', m.c.status.in_(['pending','conflict']) if status != 'active' else m.c.status == 'active',
                    or_(m.c.expires_at.is_(None), m.c.expires_at > now()) if status == 'active' else True))
                if origin == 'ai' and count >= (self.active_limit if status == 'active' else self.pending_limit):
                    return dict(outcome='rejected', reason='Automatic memory capacity reached. Manage memories in Settings.')
                # Manual memories also have a transparent hard bound; no silent eviction.
                if session.scalar(select(func.count()).select_from(m).where(m.c.learner_id == owner)) >= 1000:
                    raise AppError('MEMORY_CAPACITY', 'Memory capacity reached (1000). Delete unused memories first.', 409)
                identifier, revision = str(uuid4()), 1
                session.execute(m.insert().values(id=identifier, learner_id=owner, content=content, fingerprint=claim_hash,
                    category=category, status=status, origin=origin, revision=revision, pinned=pinned,
                    conflicts=conflicts,
                    created_at=stamp, updated_at=stamp, confirmed_at=stamp if status == 'active' else None, expires_at=expires_at))
            if evidence:
                session.execute(e.insert().values(id=str(uuid4()), learner_id=owner, memory_id=identifier, **evidence))
            else:
                session.execute(e.insert().values(id=str(uuid4()), learner_id=owner, memory_id=identifier,
                    quote=content, source_date=stamp, source_deleted=False, explicit_consent=True))
            self._revision(session, owner, identifier, revision, origin)
            outcome = 'saved' if status == 'active' else status
            self._receipt(session, owner, operation, outcome, identifier, scope, request_hash)
            return dict(outcome=outcome, memory=self._public(self._get(session, owner, identifier)))

    def edit(self, owner, identifier, body):
        from app.history_management.memory.validation import SECRET
        if body.content is not None and SECRET.search(body.content):
            raise AppError('MEMORY_SECRET', 'Do not store passwords, credentials or secrets in memory.', 422)
        with self.sessions.begin() as session:
            self._lock(session, owner)
            row = self._get(session, owner, identifier)
            if row['revision'] != body.expected_revision:
                raise conflict()
            values = dict(revision=row['revision'] + 1, updated_at=now(), origin='manual')
            if row['status'] == 'conflict' and (body.confirm or body.content is not None):
                if not body.resolve_conflict:
                    raise AppError('MEMORY_CONFLICT_REVIEW', 'Review and explicitly resolve the conflicting records first.', 409)
                reviewed = {str(key): value for key, value in body.conflict_revisions.items()} if body.conflict_revisions is not None else None
                if reviewed is not None and set(reviewed) != {x['memory_id'] for x in row['conflicts']}:
                    raise conflict()
                for reference in row['conflicts']:
                    other = self._get(session, owner, reference['memory_id'])
                    if other['revision'] != (reviewed[other['id']] if reviewed is not None else reference['revision']):
                        raise conflict()
                    session.execute(update(m).where(m.c.learner_id == owner, m.c.id == other['id']).values(status='conflict', revision=other['revision'] + 1, updated_at=now(),
                        conflicts=[dict(memory_id=identifier, revision=row['revision']+1, content=body.content or row['content'])]))
                    self._revision(session, owner, other['id'], other['revision'] + 1, 'manual')
                values['conflicts'] = []
            if body.content is not None:
                values.update(content=body.content, fingerprint=fingerprint(body.content), status='active', confirmed_at=now())
                duplicate = session.execute(select(m.c.id).where(m.c.learner_id == owner, m.c.fingerprint == values['fingerprint'], m.c.id != identifier)).first()
                if duplicate:
                    raise AppError('MEMORY_DUPLICATE', 'That memory already exists.', 409)
                if values['fingerprint'] != row['fingerprint']:
                    # A user correction retires the previous claim/evidence too.
                    # Otherwise an AI can recreate the obsolete fact later.
                    retired = [row['fingerprint']] + [source_fingerprint(x) for x in session.scalars(select(e.c.message_id)
                        .where(e.c.learner_id == owner, e.c.memory_id == identifier, e.c.message_id.is_not(None)))]
                    for key in retired:
                        session.execute(insert(s).values(learner_id=owner, fingerprint=key, created_at=now()).on_conflict_do_nothing())
                values['expires_at'] = None  # A new explicit assertion refreshes applicability.
                session.execute(delete(e).where(e.c.learner_id == owner, e.c.memory_id == identifier))
                session.execute(e.insert().values(id=str(uuid4()), learner_id=owner, memory_id=identifier,
                    quote=body.content, source_date=now(), source_deleted=False, explicit_consent=True))
            if body.confirm:
                values.update(status='active', confirmed_at=now())
            if body.pinned is not None:
                values['pinned'] = body.pinned
            if body.clear_expiration or body.expires_at:
                values['expires_at'] = None if body.clear_expiration else body.expires_at
            session.execute(update(m).where(m.c.learner_id == owner, m.c.id == identifier).values(**values))
            self._revision(session, owner, identifier, values['revision'], 'manual')
            return self._public(dict(row, **values))

    def maintain(self, owner, limit=100):
        from datetime import timedelta
        with self.sessions.begin() as session:
            self._lock(session, owner)
            old = now() - timedelta(days=90)
            candidates = list(session.scalars(select(m.c.id).where(m.c.learner_id == owner, m.c.status != 'active', m.c.origin == 'ai', m.c.pinned.is_(False), m.c.confirmed_at.is_(None), m.c.updated_at < old).limit(limit)))
            if candidates:
                session.execute(update(rc).where(rc.c.learner_id == owner, rc.c.memory_id.in_(candidates)).values(memory_id=None, outcome='rejected'))
                session.execute(delete(m).where(m.c.learner_id == owner, m.c.id.in_(candidates)))
            keys = list(session.scalars(select(rc.c.operation_key).where(rc.c.learner_id == owner, rc.c.created_at < old).limit(limit)))
            if keys:
                session.execute(delete(rc).where(rc.c.learner_id == owner, rc.c.operation_key.in_(keys)))
            return dict(expired_candidates=len(candidates), expired_receipts=len(keys))

    def remove(self, owner, identifier, revision):
        with self.sessions.begin() as session:
            self._lock(session, owner)
            row = self._get(session, owner, identifier)
            if row['revision'] != revision:
                raise conflict()
            hashes = [row['fingerprint']] + [source_fingerprint(x) for x in session.scalars(select(e.c.message_id).where(e.c.learner_id == owner, e.c.memory_id == identifier, e.c.message_id.is_not(None)))]
            for value in hashes:
                session.execute(insert(s).values(learner_id=owner, fingerprint=value, created_at=now()).on_conflict_do_nothing())
            session.execute(update(rc).where(rc.c.learner_id == owner, rc.c.memory_id == identifier).values(memory_id=None, outcome='rejected'))
            # Conflict snapshots are also personal content; remove every cached
            # copy of a forgotten claim, without silently activating candidates.
            dependents = session.execute(select(m).where(m.c.learner_id == owner, m.c.conflicts.contains([{'memory_id': identifier}]))).mappings().all()
            for dependent in dependents:
                session.execute(update(m).where(m.c.id == dependent['id'], m.c.learner_id == owner).values(
                    conflicts=[x for x in dependent['conflicts'] if x['memory_id'] != identifier], revision=dependent['revision']+1, updated_at=now()))
                self._revision(session, owner, dependent['id'], dependent['revision']+1, 'manual')
            session.execute(delete(m).where(m.c.learner_id == owner, m.c.id == identifier))
            return dict(deleted=True)

    @staticmethod
    def references_current(session, owner, payload):
        for reference in payload.get('memory_references', []):
            row = session.execute(select(m.c.revision).where(m.c.learner_id == owner, m.c.id == reference['memory_id'], m.c.status == 'active',
                or_(m.c.expires_at.is_(None), m.c.expires_at > now()))).first()
            if not row or row[0] != reference['revision']:
                return False
        if payload.get('history_references'):
            from app.chat.repositories.tables import conversations
            ids = {x['conversation_id'] for x in payload['history_references']}
            found = set(session.scalars(select(conversations.c.id).where(conversations.c.learner_id == owner, conversations.c.id.in_(ids), conversations.c.deleted_at.is_(None))))
            if found != ids:
                return False
        return True

    @staticmethod
    def detach_chat(session, owner, conversation_id):
        """Called inside chat deletion's transaction under its existing owner lock."""
        candidates = select(e.c.memory_id).where(e.c.learner_id == owner, e.c.conversation_id == conversation_id)
        other_evidence = e.alias('other_evidence')
        has_other_source = select(other_evidence.c.id).where(other_evidence.c.learner_id == owner, other_evidence.c.memory_id == m.c.id,
            other_evidence.c.conversation_id != conversation_id, other_evidence.c.source_deleted.is_(False)).exists()
        session.execute(delete(m).where(m.c.learner_id == owner, m.c.status != 'active', m.c.origin == 'ai', m.c.pinned.is_(False),
            m.c.confirmed_at.is_(None), m.c.id.in_(candidates), ~has_other_source))
        session.execute(update(e).where(e.c.learner_id == owner, e.c.conversation_id == conversation_id).values(source_deleted=True))
        session.execute(delete(rc).where(rc.c.learner_id == owner, rc.c.conversation_id == conversation_id))
