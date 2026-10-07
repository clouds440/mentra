from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

from app.learner.normalization import normalize
from app.learner.repositories.tables import learning_evidence as evidence, misconception as misconceptions
from .base import PostgresRepositoryBase, utcnow


class EvidenceStore(PostgresRepositoryBase):
    def append_evidence(self, value):
        values = self._owned_values(value)
        values['metadata_json'] = values.pop('metadata') or {}
        values['evidence_confidence'] = value.evidence_confidence if value.evidence_confidence is not None else 1
        with self._session() as session:
            session.execute(insert(evidence).values(**values))

    def get_evidence(self, evidence_id, learner_id):
        with self._session() as session:
            return self._evidence_from_row(session.execute(select(evidence).where(
                evidence.c.id == evidence_id, evidence.c.learner_id == learner_id)).mappings().first())

    def find_evidence_by_source(self, learner_id, source_type, source_id, concept_id):
        with self._session() as session:
            return self._evidence_from_row(session.execute(select(evidence).where(
                evidence.c.learner_id == learner_id, evidence.c.source_type == source_type,
                evidence.c.source_id == source_id, evidence.c.concept_id == concept_id)).mappings().first())

    def list_evidence(self, learner_id, concept_id):
        with self._session() as session:
            return [self._evidence_from_row(row) for row in session.execute(select(evidence).where(
                evidence.c.learner_id == learner_id, evidence.c.concept_id == concept_id).order_by(evidence.c.occurred_at, evidence.c.id)).mappings()]

    def list_misconceptions(self, learner_id, concept_id):
        with self._session() as session:
            return [self._misconception_from_row(row) for row in session.execute(select(misconceptions).where(
                misconceptions.c.learner_id == learner_id, misconceptions.c.concept_id == concept_id,
                misconceptions.c.status == 'ACTIVE').order_by(misconceptions.c.confidence.desc(), misconceptions.c.last_observed_at.desc())).mappings()]

    def save_misconception(self, value):
        stmt = insert(misconceptions).values(**self._owned_values(value), normalized_description=normalize(value.description))
        with self._session() as session:
            return session.execute(stmt.on_conflict_do_update(index_elements=['learner_id','concept_id','normalized_description'],
                set_=dict(confidence=value.confidence, status='ACTIVE', last_observed_at=utcnow(), resolved_at=None)).returning(misconceptions.c.id)).scalar_one()

    def misconceptions_for_concepts(self, learner_id, concept_ids):
        ranked = select(misconceptions.c.concept_id, misconceptions.c.description,
            func.row_number().over(partition_by=misconceptions.c.concept_id,
                                   order_by=misconceptions.c.confidence.desc()).label('position')).where(
            misconceptions.c.learner_id == learner_id, misconceptions.c.concept_id.in_(concept_ids),
            misconceptions.c.status == 'ACTIVE', misconceptions.c.confidence >= 0.8).subquery()
        result = {}
        with self._session() as session:
            for row in session.execute(select(ranked).where(ranked.c.position <= 3)).mappings():
                result.setdefault(row['concept_id'], []).append(row['description'])
        return result
