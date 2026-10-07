"""Explainable, configurable priority policies; bounded top-K output."""

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from app.learner.models import LearnerConceptState


class RankingPolicy(Protocol):
    def score(self, state: LearnerConceptState | None, retention: float | None,
              prerequisites: int, relevance: float, verification: bool = False) -> tuple[float, str]: ...


@dataclass(frozen=True)
class WeightedRankingPolicy:
    weakness_weight: float = 0.4
    retention_weight: float = 0.2
    uncertainty_weight: float = 0.2
    prerequisite_weight: float = 0.1
    relevance_weight: float = 0.1

    def __post_init__(self):
        weights = [self.weakness_weight, self.retention_weight, self.uncertainty_weight,
                   self.prerequisite_weight, self.relevance_weight]
        if any(not isfinite(value) or value < 0 for value in weights) or sum(weights) <= 0:
            raise ValueError('Ranking weights must be finite, non-negative, and have a positive sum')

    def score(self, state, retention, prerequisites, relevance, verification=False):
        if state is None or state.mastery is None:
            return 0.9 if verification else 0.8, 'insufficient_evidence'
        uncertainty = 1 - (state.estimate_confidence or 0)
        retention_risk = 1 - (retention if retention is not None else 0)
        if state.verification_required:
            return 1.0, 'contradictory_evidence'
        weakness = 1 - state.mastery
        if verification:
            priority = 0.45 * uncertainty + 0.35 * retention_risk + 0.1 * min(1, prerequisites / 3) + 0.1 * relevance
            reason = 'low_estimate_confidence' if uncertainty >= retention_risk else 'retention_uncertain'
        else:
            priority = (self.weakness_weight * weakness + self.retention_weight * retention_risk +
                        self.uncertainty_weight * uncertainty + self.prerequisite_weight * min(1, prerequisites / 3) +
                        self.relevance_weight * relevance)
            priority /= (self.weakness_weight + self.retention_weight + self.uncertainty_weight +
                         self.prerequisite_weight + self.relevance_weight)
            reason = max(((weakness * self.weakness_weight, 'low_mastery'),
                          (retention_risk * self.retention_weight, 'retention_uncertain'),
                          (uncertainty * self.uncertainty_weight, 'low_estimate_confidence'),
                          (min(1, prerequisites / 3) * self.prerequisite_weight, 'prerequisite_importance')))[1]
        return min(1, max(0, priority)), reason
