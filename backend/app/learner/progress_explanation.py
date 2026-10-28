"""Bounded, deterministic support for estimates; never expose raw policy or metadata."""
from datetime import datetime
from uuid import UUID
from app.core.exceptions import AppError
from .schemas import ProgressExplanation, ProgressEvidence
from .scoring.signals import diagnostics


def identifier(value):
    try: return UUID(str(value)) if value else None
    except (ValueError, TypeError, AttributeError): return None


def explain(engine, owner, concept_id, context_id=None):
    contexts = engine.contexts.select(owner, [context_id] if context_id else None)
    concepts = engine.repository.context_concepts(owner, [c.id for c in contexts], concept_ids=[concept_id], limit=1)
    if not concepts:
        raise AppError('LEARNING_TOPIC_UNAVAILABLE', 'This topic is unavailable in your learning contexts.', 404)
    concept = concepts[0]
    membership = engine.repository.skill_memberships(owner, [concept.id]).get(concept.id, {})
    factor = engine.repository.context_factors(owner, contexts, [concept.id]).get(concept.id, {})
    engine.states.load(owner, [concept.id])  # Refresh a stale policy before the read snapshot.
    with engine.repository.transaction(learner_ids=[owner]) as repository:
        state = repository.get_state(owner, concept.id)
        recent = repository.recent_accepted_evidence(owner, concept.id)
    retention = engine.retention_policy.calculate(state, engine.clock()) if state else None
    info = diagnostics(state, retention)
    data = state.policy_data if state else {}
    observations = []
    for item in recent:
        metadata = item.metadata or {}
        repeated = (item.attempt_number or 1) > 1 or bool(metadata.get('known_exposure'))
        independent = not repeated and item.independence is not None and item.independence >= .8 and item.hint_count == 0
        participation = 'repeated' if repeated else 'independent' if independent else 'assisted' if item.hint_count or item.independence is not None else 'unspecified'
        assessment_id, attempt_id = identifier(metadata.get('assessment_id')), identifier(metadata.get('attempt_id'))
        revision = item.item_revision if assessment_id and attempt_id else None
        observations.append(ProgressEvidence(occurred_at=item.occurred_at, source_type=item.source_type,
            result=item.result, difficulty=item.difficulty, independent=independent, participation=participation,
            assessment_id=assessment_id, attempt_id=attempt_id, grade_revision=revision))
    next_check = ('Try a few new questions without hints to build an initial estimate.' if info['knowledge_status']=='insufficient_evidence'
        else 'Check your understanding with new questions without hints.' if info['knowledge_status']=='needs_verification'
        else 'Practise with new questions at the suggested difficulty.')
    return ProgressExplanation(concept_id=concept.id, context_id=factor.get('context_id'), name=membership.get('label', concept.canonical_name), **{key:info[key] for key in
        ('knowledge_status','mastery_lower_bound','mastery_upper_bound','independent_item_count','recommended_difficulty')},
        mastery=state.mastery if state else None, evidence_count=state.evidence_count if state else 0,
        last_practice_at=state.last_evidence_at if state else None,
        last_independent_at=datetime.fromisoformat(data['last_independent_at']) if data.get('last_independent_at') else None,
        next_check=next_check, difficulty_coverage=[dict(band=band, independent_items=len(data.get(f'{band}_items', [])))
            for band in ('easy','medium','hard')], recent_evidence=observations, generated_at=engine.clock())
