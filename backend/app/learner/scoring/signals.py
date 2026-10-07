"""Read-only skill diagnostics; uncertainty is explicit, never fabricated certainty."""

from math import sqrt
from datetime import datetime

from app.learner.models import LearnerConceptState


def difficulty_band(difficulty: float) -> str:
    return 'easy' if difficulty < 0.35 else ('medium' if difficulty < 0.7 else 'hard')


def estimate_interval(success: float, weight: float) -> tuple[float, float]:
    if weight <= 0:
        return 0.0, 1.0
    alpha, beta = 0.5 + success, 0.5 + max(0, weight - success)
    mean = alpha / (alpha + beta)
    radius = 1.96 * sqrt(alpha * beta / ((alpha + beta)**2 * (alpha + beta + 1)))
    return max(0, mean - radius), min(1, mean + radius)


def skill_estimate(data: dict, confidence_policy) -> tuple[float, float, str]:
    bands = [band for band in ('easy', 'medium', 'hard') if data.get(f'{band}_weight', 0) > 0]
    supported = [band for band in bands if data[f'{band}_weight'] >= 2 and len(data.get(f'{band}_items', [])) >= 3]
    band = max(supported or bands, key=lambda b: (0.5 + data[f'{b}_capability']) / (1 + data[f'{b}_weight']))
    weight, success = data[f'{band}_weight'], data[f'{band}_success']
    mean = success / weight
    variance = max(0, data[f'{band}_squares'] / weight - mean**2)
    confidence = confidence_policy.calculate(weight, variance, data[f'{band}_difficulty'] / weight)
    confidence *= min(1, len(data.get(f'{band}_items', [])) / 5)
    if data[f'{band}_assessment_weight'] < 2:
        confidence = min(confidence, 0.55)
    return (0.5 + data[f'{band}_capability']) / (1 + weight), confidence, band


def recommended_difficulty(state: LearnerConceptState | None) -> float:
    if not state or state.mastery is None:
        return 0.3
    if state.verification_required:
        return float(state.policy_data.get('verification_difficulty', 0.5))
    for band, level in [('hard', 0.8), ('medium', 0.5), ('easy', 0.2)]:
        weight = state.policy_data.get(f'{band}_weight', 0)
        success = state.policy_data.get(f'{band}_success', 0)
        if weight >= 2 and len(state.policy_data.get(f'{band}_items', [])) >= 3 and success / weight >= 0.75:
            return min(0.9, level + 0.1)
    return 0.3


def diagnostics(state: LearnerConceptState | None, retention: float | None = None) -> dict:
    if not state:
        return dict(knowledge_status='insufficient_evidence', mastery_lower_bound=0,
                    mastery_upper_bound=1, independent_item_count=0, recommended_difficulty=0.3)
    data = state.policy_data
    band = data.get('mastery_band', '')
    lower, upper = estimate_interval(data.get(f'{band}_capability', 0), data.get(f'{band}_weight', 0))
    items = len(data.get('independent_items', []))
    if state.verification_required:
        status = 'needs_verification'
    elif state.mastery is None or items < 3 or (state.estimate_confidence or 0) < 0.4:
        status = 'insufficient_evidence'
    elif state.mastery < 0.45:
        status = 'needs_practice'
    elif retention is not None and retention < 0.5:
        status = 'needs_verification'
    elif state.mastery >= 0.75 and (state.estimate_confidence or 0) >= 0.65:
        status = 'demonstrated'
    else:
        status = 'developing'
    return dict(knowledge_status=status, mastery_lower_bound=lower, mastery_upper_bound=upper,
                independent_item_count=items, recommended_difficulty=recommended_difficulty(state))


def performance_estimate(state: LearnerConceptState | None, difficulty: float,
                         now: datetime) -> tuple[float, float, float, bool, float]:
    if state is None:
        return 0.5, 0, 1, False, 0
    band = difficulty_band(difficulty)
    weight = state.policy_data.get(f'{band}_weight', 0)
    success = state.policy_data.get(f'{band}_success', 0)
    if weight < 2 or len(state.policy_data.get(f'{band}_items', [])) < 3:
        return 0.5, 0, 1, False, weight
    mean = (0.5 + success) / (1 + weight)
    lower, upper = estimate_interval(success, weight)
    last = state.policy_data.get(f'{band}_last_at')
    age = max(0, (now - datetime.fromisoformat(last)).total_seconds() / 86400) if last else float('inf')
    reliability = 2 ** (-max(0, age - 7) / 30)
    # Stale knowledge increases uncertainty in future performance; it does not
    # rewrite evidence-based mastery. These intervals remain heuristic, not calibrated.
    return (0.5 + reliability * (mean - 0.5), reliability * lower,
            1 - reliability * (1 - upper), True, weight)
