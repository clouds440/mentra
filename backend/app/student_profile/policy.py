"""Centralized, bounded adaptation of estimates. Never writes profile facts."""
from .schemas import DIMENSIONS, Estimates, Estimate, AIEvaluation, ProfileEvidence, ProfileContext, StudentProfile
from .errors import EvaluationUnavailable

POLICY_VERSION = 'broad-profile-conservative-v1'


def context_packet(profile: StudentProfile) -> ProfileContext | None:
    if profile.details is None:
        return None
    return ProfileContext(details=profile.details, estimates={dimension: {
        'value': getattr(profile.estimates, dimension).value,
        'confidence': getattr(profile.estimates, dimension).confidence,
    } for dimension in DIMENSIONS})


def dimension_items(evidence, dimension):
    return [item for item in evidence.input.items if dimension == 'overall_proficiency' or item.dimension == dimension]


def validate_evaluation(evaluation: AIEvaluation, evidence: ProfileEvidence):
    for dimension in DIMENSIONS:
        candidate = getattr(evaluation, dimension)
        allowed = {item.id for item in dimension_items(evidence, dimension)}
        if len(set(candidate.evidence_ids)) != len(candidate.evidence_ids) or not set(candidate.evidence_ids) <= allowed:
            raise EvaluationUnavailable('Evaluator cited unsupported evidence')
        if candidate.value is not None and not candidate.evidence_ids:
            raise EvaluationUnavailable('An estimate requires supporting evidence')


def apply_estimates(current: Estimates, evidence: ProfileEvidence, evaluation: AIEvaluation) -> Estimates:
    validate_evaluation(evaluation, evidence)
    result = current.model_copy(deep=True)
    for dimension in DIMENSIONS:
        items = dimension_items(evidence, dimension)
        if not items:
            continue
        previous = getattr(current, dimension)
        candidate = getattr(evaluation, dimension)
        # One large event cannot overwhelm accumulated observations. Interaction
        # extraction is intentionally weaker than independently scored assessment.
        reliability = min(evidence.input.reliability, .35) if evidence.input.source_type == 'interaction' else evidence.input.reliability
        unit_weight = reliability * min(1, 8 / len(evidence.input.items))
        weight = previous.effective_weight + len(items) * unit_weight
        successes = previous.successful_weight + sum(item.correct for item in items) * unit_weight
        count = previous.evidence_count + len(items)
        sources = previous.source_count + 1
        value, confidence, rationale = previous.value, previous.confidence, previous.rationale
        if candidate.value is not None and count >= 2 and weight >= 1:
            # Anchor the AI to deterministic accumulated results. These remain
            # level-relative heuristics, never calibrated probabilities or IQ.
            anchor = (successes + 1) / (weight + 2)
            proposed = max(anchor - .15, min(anchor + .15, candidate.value))
            if previous.value is None:
                value = proposed
            else:
                shift = .08 * min(1, len(items) * unit_weight / 4)
                value = max(previous.value - shift, min(previous.value + shift, proposed))
            cap = min(.75 if sources >= 3 else .55, weight / (weight + 6))
            target_confidence = min(cap, candidate.confidence)
            confidence = target_confidence if previous.value is None else max(previous.confidence - .05, min(target_confidence, previous.confidence + .05))
            rationale = candidate.rationale
        timestamp = max(filter(None, [previous.last_evidence_at, evidence.input.occurred_at]))
        setattr(result, dimension, Estimate(value=None if value is None else round(max(0, min(1, value)), 4),
            confidence=round(confidence, 4), evidence_count=count, source_count=sources,
            effective_weight=weight, successful_weight=successes, last_evidence_at=timestamp, rationale=rationale))
    return result
