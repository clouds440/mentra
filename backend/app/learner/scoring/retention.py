from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from app.learner.models import LearnerConceptState


@dataclass(frozen=True)
class ExponentialRetentionPolicy:
    version: str = 'retention-v2'
    base_half_life_days: float = 30

    def __post_init__(self):
        if not isfinite(self.base_half_life_days) or self.base_half_life_days <= 0:
            raise ValueError('Retention half-life must be positive and finite')

    def calculate(self, state: LearnerConceptState, now: datetime) -> float | None:
        anchor = state.last_demonstrated_at
        if anchor is None or state.retention_confidence is None:
            return None
        age = max(0, (now - anchor).total_seconds() / 86400)
        # One exam with twenty questions is not twenty spaced recall sessions.
        days = len(state.policy_data.get('recall_days', []))
        stability = 1 + max(0, days - 1) * 0.3
        return state.retention_confidence * 2 ** (-age / (self.base_half_life_days * stability))
