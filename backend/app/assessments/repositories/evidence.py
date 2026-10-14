"""Revision-fenced durable outbox for learning updates after results publish."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, and_, or_
from app.core.exceptions import AppError
from .tables import evidence_jobs as j, attempts as t


class AssessmentEvidenceJobs:
    def __init__(self, repository):
        self.repository = repository

    def claim(self):
        repo = self.repository
        now = repo.clock()
        with repo.sessions() as session:
            # A crashed final retry must not leave the public status pending.
            expired = session.execute(select(j.c.attempt_id, j.c.grade_revision, j.c.learner_id).where(
                j.c.state == 'running', j.c.attempts >= 3, j.c.claim_until <= now).limit(32)).all()
            candidates = session.execute(select(j).where(j.c.attempts < 3,
                or_(j.c.state == 'queued', and_(j.c.state == 'running', j.c.claim_until <= now),
                    and_(j.c.state == 'failed', j.c.retry_at <= now)))
                .order_by(j.c.created_at, j.c.attempt_id).limit(32)).mappings().all()
        # Preserve the owner-first lock order used by publication and corrections.
        for identifier, revision, owner in expired:
            with repo.transactions.try_write(owner) as tx:
                if tx is None: continue
                changed = tx._session.execute(update(j).where(j.c.attempt_id == identifier,
                    j.c.grade_revision == revision, j.c.state == 'running', j.c.attempts >= 3,
                    j.c.claim_until <= now).values(state='failed', claim_id=None, claim_until=None)).rowcount
                if changed:
                    tx._session.execute(update(t).where(t.c.id == identifier, t.c.learner_id == owner,
                        t.c.grade_revision == revision, t.c.evidence_status == 'pending')
                        .values(evidence_status='unavailable', revision=t.c.revision + 1))
        for candidate in candidates:
            with repo.transactions.try_write(candidate['learner_id']) as tx:
                if tx is None: continue
                key = and_(j.c.attempt_id == candidate['attempt_id'], j.c.grade_revision == candidate['grade_revision'])
                row = tx._session.execute(select(j).where(key)).mappings().first()
                if not row or row['attempts'] >= 3 or row['state'] in ('applied', 'skipped'):
                    continue
                if row['claim_until'] and row['claim_until'] > now or row['state'] == 'failed' and (not row['retry_at'] or row['retry_at'] > now):
                    continue
                attempt = repo._attempt(tx._session, row['learner_id'], row['attempt_id'])
                if attempt['grade_revision'] != row['grade_revision'] or attempt['state'] != 'graded':
                    tx._session.execute(update(j).where(key).values(state='skipped', claim_id=None, claim_until=None))
                    continue
                claim = str(uuid4())
                tx._session.execute(update(j).where(key).values(state='running', claim_id=claim,
                    claim_until=now + timedelta(seconds=180), attempts=row['attempts'] + 1))
                return dict(id=row['attempt_id'], owner=row['learner_id'], grade_revision=row['grade_revision'],
                    claim_id=claim, attempt=attempt, assessment=repo._assessment(tx._session, row['learner_id'], attempt['assessment_id']),
                    profile_context_version=attempt['profile_context_version'])
        return None

    def complete(self, job, apply):
        repo = self.repository
        with repo.transactions.write(job['owner']) as tx:
            key = and_(j.c.attempt_id == job['id'], j.c.grade_revision == job['grade_revision'])
            row = tx._session.execute(select(j).where(key)).mappings().first()
            if not row or row['state'] == 'applied': return
            if row['claim_id'] != job['claim_id'] or row['claim_until'] <= repo.clock():
                raise AppError('ATTEMPT_CLAIM_EXPIRED', 'Learning update ownership changed.', 409)
            attempt = repo._attempt(tx._session, job['owner'], job['id'])
            if attempt['grade_revision'] != job['grade_revision'] or attempt['state'] != 'graded':
                tx._session.execute(update(j).where(key).values(state='skipped', claim_id=None, claim_until=None))
                return
            receipt = apply(tx)
            expected = sum(len(grade['concept_grades']) for grade in attempt['grades'])
            accepted = sum(bool(item.get('accepted')) for item in receipt or [])
            status = 'applied' if accepted == expected else 'partial' if accepted else 'unavailable'
            tx._session.execute(update(t).where(t.c.id == job['id']).values(evidence_status=status,
                evidence_receipt=receipt, revision=t.c.revision + 1))
            tx._session.execute(update(j).where(key).values(state='applied', claim_id=None, claim_until=None, retry_at=None))

    def fail(self, job):
        repo = self.repository
        with repo.transactions.write(job['owner']) as tx:
            key = and_(j.c.attempt_id == job['id'], j.c.grade_revision == job['grade_revision'], j.c.claim_id == job['claim_id'])
            row = tx._session.execute(select(j).where(key)).mappings().first()
            if not row: return
            tx._session.execute(update(j).where(key).values(state='failed', claim_id=None, claim_until=None,
                retry_at=repo.clock() + timedelta(seconds=5 * 2 ** row['attempts']) if row['attempts'] < 3 else None))
            if row['attempts'] >= 3:
                tx._session.execute(update(t).where(t.c.id == job['id'], t.c.grade_revision == job['grade_revision'])
                    .values(evidence_status='unavailable', revision=t.c.revision + 1))
