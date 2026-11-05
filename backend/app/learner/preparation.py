"""Bounded, read-only assessment preparation without registry-wide ranking."""
from dataclasses import dataclass, replace
from .models import Concept
from .schemas import LearnerContextPacket
from .normalization import query_terms, normalize
from app.core.exceptions import AppError


@dataclass(frozen=True)
class AssessmentContext:
    packet: LearnerContextPacket
    concepts: dict[str, Concept]
    memberships: dict[str, dict]


def prepare(engine, owner, context_id, query, concept_ids=()):
    with engine.read_scope() as scoped:
        context = replace(scoped.contexts.require(owner, context_id), relevance_score=1)
        ids = list(dict.fromkeys(str(value) for value in concept_ids))
        if len(ids) > 20:
            raise AppError('ASSESSMENT_TARGET_UNAVAILABLE', 'Choose up to twenty available practice targets.', 422)
        # Exact targets are mandatory. A topical lookup may return no prior
        # knowledge; never substitute an unrelated historical weakness.
        concepts = scoped.repository.context_concepts(owner, [context_id],
            **(dict(concept_ids=ids, limit=20) if ids else dict(query_terms=query_terms(query),
                normalized_query=normalize(query), limit=8))) if ids or query_terms(query) else []
        found = {value.id: value for value in concepts}
        if ids and set(found) != set(ids):
            raise AppError('ASSESSMENT_TARGET_UNAVAILABLE', 'A practice topic is no longer available in this learning context.', 404)
        if ids:
            concepts = [found[key] for key in ids]
        memberships = scoped.repository.skill_memberships(owner, [value.id for value in concepts]) if concepts else {}
        scoped.retrieval._membership_cache = {value.id: memberships.get(value.id) for value in concepts}
        scoped.states._read_only = True
        packet = LearnerContextPacket(active_contexts=[context.name] if context.status == 'ACTIVE' else [],
            context_ids=[context_id], concepts=scoped.retrieval.project(owner, concepts[:8], [context]) if concepts else [],
            generated_at=engine.clock())
        labeled = {value.id: replace(value, canonical_name=memberships.get(value.id, {}).get('label', value.canonical_name)) for value in concepts}
        return AssessmentContext(packet, labeled, memberships)
