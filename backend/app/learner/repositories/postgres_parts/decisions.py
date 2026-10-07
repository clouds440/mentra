from dataclasses import replace

from sqlalchemy import select, update, or_
from sqlalchemy.dialects.postgresql import insert

from app.learner.repositories.tables import learning_evidence as evidence, evidence_decision as decisions, concept_redirect as redirects, learner_audit as audits
from .base import PostgresRepositoryBase, utcnow


class DecisionStore(PostgresRepositoryBase):
    def save_decision(self, evidence_id, status, reason, learner_id):
        with self._session() as session:
            session.execute(insert(decisions).values(evidence_id=evidence_id, learner_id=learner_id, status=status, reason=reason))

    def get_decision(self, evidence_id, learner_id):
        with self._session() as session:
            row = session.execute(select(decisions).where(decisions.c.evidence_id == evidence_id,
                                  decisions.c.learner_id == learner_id)).mappings().first()
            return dict(row) if row else None

    def confirm_decision(self, evidence_id, source, learner_id):
        with self._session() as session:
            session.execute(update(decisions).where(decisions.c.evidence_id == evidence_id,
                decisions.c.learner_id == learner_id, decisions.c.status == 'PENDING').values(
                status='ACCEPTED', reason='confirmed', confirmed_at=utcnow(), confirmation_source=source))

    def supersede_decision(self, evidence_id, learner_id):
        original = self.get_evidence(evidence_id, learner_id)
        canonical = self.canonical_id(original.concept_id)
        ids = select(evidence.c.id).outerjoin(redirects, redirects.c.source_id == evidence.c.concept_id).where(
            evidence.c.learner_id == learner_id, evidence.c.source_type == original.source_type,
            evidence.c.source_id == original.source_id, or_(evidence.c.concept_id == canonical, redirects.c.target_id == canonical))
        with self._session() as session:
            session.execute(update(decisions).where(decisions.c.learner_id == learner_id,
                decisions.c.status == 'ACCEPTED', decisions.c.evidence_id.in_(ids)).values(status='SUPERSEDED', reason='corrected'))

    def accepted_evidence(self, learner_id, concept_id):
        stmt = select(evidence, decisions.c.confirmed_at).join(decisions, decisions.c.evidence_id == evidence.c.id).outerjoin(
            redirects, redirects.c.source_id == evidence.c.concept_id).where(evidence.c.learner_id == learner_id,
            decisions.c.learner_id == learner_id, decisions.c.status == 'ACCEPTED',
            or_(evidence.c.concept_id == concept_id, redirects.c.target_id == concept_id)).order_by(evidence.c.occurred_at, decisions.c.sequence)
        result, seen = [], set()
        with self._session() as session:
            for row in session.execute(stmt).mappings():
                key = (row['source_type'], row['source_id']) if row['source_id'] else ('id', row['id'])
                if key not in seen:
                    item = self._evidence_from_row(row)
                    result.append(replace(item, extraction_confidence=1) if row['confirmed_at'] else item)
                    seen.add(key)
        return result

    def latest_item_evidence(self, learner_id, concept_id, item_id, source_type=None, attempt_number=None, session_id=None):
        filters = [evidence.c.learner_id == learner_id, evidence.c.item_id == item_id,
                   decisions.c.learner_id == learner_id, decisions.c.status == 'ACCEPTED',
                   or_(evidence.c.concept_id == concept_id, redirects.c.target_id == concept_id)]
        if source_type:
            filters.append(evidence.c.source_type == source_type)
        if attempt_number is not None:
            from sqlalchemy import func
            filters.append(func.coalesce(evidence.c.attempt_number, 1) == attempt_number)
        if session_id is not None:
            filters.append(evidence.c.session_id == session_id)
        with self._session() as session:
            return self._evidence_from_row(session.execute(select(evidence).join(decisions, decisions.c.evidence_id == evidence.c.id).outerjoin(
                redirects, redirects.c.source_id == evidence.c.concept_id).where(*filters).order_by(decisions.c.sequence.desc()).limit(1)).mappings().first())

    def find_canonical_evidence_by_source(self, learner_id, source_type, source_id, concept_id):
        with self._session() as session:
            return self._evidence_from_row(session.execute(select(evidence).outerjoin(redirects, redirects.c.source_id == evidence.c.concept_id).where(
                evidence.c.learner_id == learner_id, evidence.c.source_type == source_type, evidence.c.source_id == source_id,
                or_(evidence.c.concept_id == concept_id, redirects.c.target_id == concept_id)).order_by(evidence.c.occurred_at, evidence.c.id).limit(1)).mappings().first())

    def audit(self, action, details, learner_id=None, concept_id=None):
        with self._session() as session:
            session.execute(insert(audits).values(learner_id=learner_id, concept_id=concept_id, action=action, details_json=details))

    def list_audit(self, learner_id, concept_id, limit=50):
        with self._session() as session:
            return [dict(action=row['action'], created_at=row['created_at'], details=row['details_json']) for row in session.execute(select(audits).where(
                audits.c.learner_id == learner_id, audits.c.concept_id == concept_id).order_by(audits.c.id.desc()).limit(limit)).mappings()]
