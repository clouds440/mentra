"""Bounded recent evidence, independent capability, and challenge coverage.

This is a testable conservative baseline, not a claim of calibrated accuracy.
Old evidence fades only when new observations arrive, never from time alone.
"""

from dataclasses import dataclass, replace
from datetime import timezone
from math import isfinite

from app.learner.models import LearnerConceptState, LearningEvidence
from app.learner.scoring.confidence import HeuristicConfidencePolicy
from app.learner.scoring.contracts import ConfidencePolicy
from app.learner.scoring.signals import difficulty_band, skill_estimate


@dataclass(frozen=True)
class HeuristicMasteryPolicy:
    confidence_policy: ConfidencePolicy = HeuristicConfidencePolicy()
    version: str = 'mastery-v2'
    max_effective_weight: float = 12

    def __post_init__(self):
        if not isfinite(self.max_effective_weight) or self.max_effective_weight < 4:
            raise ValueError('Effective evidence window must be finite and at least four')

    @property
    def identity(self) -> str:
        return f'{self.version}:challenge-windows:{self.max_effective_weight}:{self.confidence_policy.version}'

    def update(self, state: LearnerConceptState, evidence: LearningEvidence) -> LearnerConceptState:
        if evidence.result == 'UNKNOWN' or (evidence.evidence_confidence or 0) <= 0:
            return state
        data = dict(state.policy_data)
        data['confidence_version'] = self.confidence_policy.version
        data['policy_identity'] = self.identity
        independence = evidence.independence
        independent = (independence is not None and independence >= 0.8 and
                       evidence.hint_count == 0 and (evidence.attempt_number or 1) == 1)
        outcome = (evidence.score / evidence.max_score if evidence.max_score else
                   {'CORRECT': 1.0, 'PARTIAL': 0.5, 'INCORRECT': 0.0}[evidence.result])
        difficulty = evidence.difficulty
        quality = (evidence.evidence_confidence or 0) * (
            evidence.extraction_confidence if evidence.extraction_confidence is not None else 1)
        channel = {'CHAT': 0.4, 'CALIBRATION': 0.8, 'MANUAL_CONFIRMATION': 0.3}.get(evidence.source_type, 1)
        assistance_known = independence is not None or evidence.hint_count > 0 or (evidence.attempt_number or 1) > 1
        hint_total = data.get('hint_observations', 0) + int(assistance_known and not independent)
        data['hint_observations'] = hint_total
        count = state.evidence_count + 1
        dependency = state.hint_dependency
        if assistance_known:
            dependency = (0.85 * dependency + 0.15 * int(not independent)
                          if dependency is not None else float(not independent))
        base = replace(state, evidence_count=count, hint_dependency=dependency,
                       last_evidence_at=evidence.occurred_at, policy_data=data, mastery_policy_version=self.version)
        # A guided success proves neither failure nor independent ability. Keep it
        # as a practice observation without manufacturing an independent mastery score.
        if not independent or difficulty is None or quality < 0.5:
            if state.mastery is not None and (dependency or 0) > 0.5:
                band = data.get('mastery_band', '')
                challenge = data.get(f'{band}_difficulty', 0) / max(1e-9, data.get(f'{band}_weight', 0))
                data['verification_difficulty'] = max(data.get('verification_difficulty', 0), challenge or 0.5)
                return replace(base, estimate_confidence=min(state.estimate_confidence or 0, 0.4),
                               verification_required=True)
            return base
        data['last_independent_at'] = evidence.occurred_at.isoformat()
        item = evidence.item_id or evidence.source_id or evidence.id
        recent = dict(data.get('recent_items', {}))
        order = list(data.get('recent_item_order', recent))
        repetitions = recent.pop(item, 0)
        recent[item] = repetitions + 1
        order = [key for key in order if key != item]
        order.append(item)
        order = order[-64:]
        # Explicit order survives repositories that serialize JSON keys sorted.
        recent = {key: recent[key] for key in order}
        data['recent_item_order'] = order
        weight = quality * channel / (1 + repetitions)**1.25
        if repetitions == 0 and evidence.item_id:
            unique = list(data.get('independent_items', []))
            if item not in unique:
                unique.append(item)
            data['independent_items'] = unique[-64:]
        data['recent_items'] = recent
        old_weight = data.get('weight', 0)
        scale = min(1, max(0, (self.max_effective_weight - weight) / old_weight)) if old_weight else 1
        for key in ['weight', 'success', 'raw_success', 'squares', 'assessment_weight']:
            data[key] = data.get(key, 0) * scale
        data['weight'] += weight
        if evidence.source_type != 'CHAT':
            data['assessment_weight'] += weight
        # Easy success supports basic capability; hard success supports transfer at
        # higher challenge. The per-band raw outcomes separately predict task scores.
        data['success'] += weight * outcome * (0.4 + 0.6 * difficulty)
        data['raw_success'] += weight * outcome
        data['squares'] += weight * outcome**2
        band = difficulty_band(difficulty)
        data[f'{band}_last_at'] = evidence.occurred_at.isoformat()
        band_weight = data.get(f'{band}_weight', 0)
        band_scale = min(1, max(0, (self.max_effective_weight - weight) / band_weight)) if band_weight else 1
        contributions = dict(weight=weight, success=weight * outcome,
                             capability=weight * outcome * (0.4 + 0.6 * difficulty),
                             squares=weight * outcome**2, difficulty=weight * difficulty,
                             assessment_weight=weight if evidence.source_type != 'CHAT' else 0)
        for metric, contribution in contributions.items():
            key = f'{band}_{metric}'
            data[key] = data.get(key, 0) * band_scale + contribution
        band_items = list(data.get(f'{band}_items', []))
        if evidence.item_id and item not in band_items:
            band_items.append(item)
        data[f'{band}_items'] = band_items[-64:]
        mastery, confidence, mastery_band = skill_estimate(data, self.confidence_policy)
        data['mastery_band'] = mastery_band
        if not evidence.item_id:
            confidence = min(confidence, 0.55)
        contradiction = (state.mastery is not None and state.mastery >= 0.7 and
                         (state.estimate_confidence or 0) >= 0.4 and outcome < 0.4 and quality >= 0.8)
        verification = state.verification_required or contradiction
        if contradiction:
            data['verification_difficulty'] = max(data.get('verification_difficulty', 0), difficulty)
            data['verification_successes'] = 0
            confidence *= 0.75
        elif verification and outcome < 0.8 and quality >= 0.8:
            data['verification_successes'] = 0
        successful = outcome >= 0.8 and quality >= 0.8 and repetitions == 0
        verified = successful and evidence.source_type != 'CHAT'
        if verification and verified and difficulty >= data.get('verification_difficulty', 0.5):
            data['verification_successes'] = data.get('verification_successes', 0) + 1
            if data['verification_successes'] >= 2:
                verification = False
        anchor, retention = state.last_demonstrated_at, state.retention_confidence
        refreshes_retention = verified and difficulty >= data.get('anchor_difficulty', 0) - 0.1
        if refreshes_retention:
            day = evidence.occurred_at.astimezone(timezone.utc).date().isoformat()
            days = list(data.get('recall_days', []))
            if day not in days:
                days.append(day)
            data['recall_days'] = days[-32:]
            data['anchor_difficulty'] = max(data.get('anchor_difficulty', 0), difficulty)
            anchor = evidence.occurred_at
            retention = min(0.95, max(0.2, confidence))
        elif outcome < 0.4 and retention is not None:
            retention *= max(0.5, 1 - 0.35 * weight)
        return replace(base, mastery=mastery, estimate_confidence=confidence,
                       retention_confidence=retention, last_demonstrated_at=anchor,
                       independent_successes=state.independent_successes + int(successful),
                       difficulty_tested=max(state.difficulty_tested or 0, difficulty),
                       last_verified_at=evidence.occurred_at if verified else state.last_verified_at,
                       verification_required=verification)
