"""Offline evaluation hooks; they never mutate production learner beliefs."""

from dataclasses import dataclass
from math import sqrt, log
from collections import defaultdict

from app.learner.models import LearnerConceptState, LearningEvidence
from app.learner.schemas import EvidenceSubmissionRequest
from app.learner.scoring import HeuristicMasteryPolicy
from app.learner.scoring.signals import performance_estimate, difficulty_band


@dataclass(frozen=True)
class Prediction:
    predicted: float
    observed: float

    def __post_init__(self):
        if not 0 <= self.predicted <= 1 or not 0 <= self.observed <= 1:
            raise ValueError('Predictions and outcomes must be finite values between zero and one')


def evaluate_predictions(predictions: list[Prediction], bins=10) -> dict[str, float | int]:
    if bins < 1:
        raise ValueError('bins must be positive')
    if not predictions:
        return {'count': 0, 'mae': 0.0, 'rmse': 0.0, 'calibration_error': 0.0}
    groups = [[] for _ in range(bins)]
    for item in predictions:
        groups[min(bins - 1, int(item.predicted * bins))].append(item)
    n = len(predictions)
    return {'count': n,
            'mae': sum(abs(p.predicted - p.observed) for p in predictions) / n,
            'rmse': sqrt(sum((p.predicted - p.observed)**2 for p in predictions) / n),
            'calibration_error': sum(abs(sum(p.predicted - p.observed for p in group)) for group in groups) / n}


def evaluate_observations(observations: list[EvidenceSubmissionRequest], *, policy=None) -> dict:
    """Predict each held-out outcome BEFORE updating isolated in-memory states.

    Supply canonical, effective accepted observations in chronological order.
    Raw correction histories must first be materialized from accepted evidence;
    this evaluator deliberately rejects them rather than leaking future regrades.
    Production persistence and learner beliefs are never touched.
    """
    policy = policy or HeuristicMasteryPolicy()
    states, seen, groups = {}, {}, defaultdict(list)
    predictions, supported, skipped = [], [], 0
    previous_time = None
    for original in observations:
        request = EvidenceSubmissionRequest.model_validate(original.model_dump())
        if previous_time and request.occurred_at < previous_time:
            raise ValueError('Evaluation observations must be chronological')
        previous_time = request.occurred_at
        if request.supersedes_evidence_id or request.item_revision != 1:
            raise ValueError('Evaluate effective observations, not raw grading revisions')
        if not request.source_id:
            raise ValueError('Evaluation requires stable observation identity')
        identity = (request.learner_id, request.concept_id, request.source_type, request.source_id)
        if identity in seen:
            if seen[identity] != request:
                raise ValueError('Evaluation source identity conflicts')
            skipped += 1
            continue
        seen[identity] = request
        extraction = request.extraction_confidence
        if (request.result == 'UNKNOWN' or request.evidence_confidence < 0.5 or
                (extraction is not None and extraction < 0.8) or
                (request.source_type == 'HANDWRITTEN_ASSESSMENT' and extraction is None)):
            skipped += 1
            continue
        key = request.learner_id, request.concept_id
        state = states.get(key)
        # Supported score predictions assume an independent first attempt at a
        # known challenge; guided/unknown observations still update practice data.
        eligible = (request.difficulty is not None and request.independence is not None and
                    request.independence >= 0.8 and request.hint_count == 0 and
                    (request.attempt_number or 1) == 1)
        if eligible:
            score, _, _, has_support, _ = performance_estimate(state, request.difficulty, request.occurred_at)
            observed = (request.score / request.max_score if request.max_score else
                        {'CORRECT': 1, 'PARTIAL': 0.5, 'INCORRECT': 0}[request.result])
            point = Prediction(score, observed)
            predictions.append(point)
            groups[f'difficulty:{difficulty_band(request.difficulty)}'].append(point)
            groups[f'student:{request.learner_id}'].append(point)
            if has_support:
                supported.append(point)
        else:
            skipped += 1
        evidence = LearningEvidence(id=request.source_id, **request.model_dump())
        states[key] = policy.update(state or LearnerConceptState(*key), evidence)
    metrics = evaluate_predictions(predictions)
    n = len(predictions)
    binary = all(p.observed in (0, 1) for p in predictions)
    metrics.update(policy_version=policy.version, supported_count=len(supported), skipped_count=skipped,
                   coverage=len(supported) / n if n else 0,
                   supported_metrics=evaluate_predictions(supported) if supported else None,
                   mean_squared_error=metrics['rmse']**2,
                   baseline_metrics=evaluate_predictions([Prediction(0.5, p.observed) for p in predictions]),
                   groups={name: evaluate_predictions(points) for name, points in sorted(groups.items())})
    if binary and n:
        metrics['brier_score'] = metrics['mean_squared_error']
        metrics['log_loss'] = -sum(p.observed * log(max(1e-9, p.predicted)) +
                                  (1 - p.observed) * log(max(1e-9, 1 - p.predicted)) for p in predictions) / n
    return metrics
