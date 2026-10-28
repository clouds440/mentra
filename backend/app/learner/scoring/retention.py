from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from app.learner.models import LearnerConceptState


def observation_freshness(state: LearnerConceptState, occurred_at: datetime, now: datetime,
                          base_half_life_days: float = 30, band: str | None = None) -> float:
    if band is None:
        from .signals import difficulty_band
        band = difficulty_band(state.policy_data.get('anchor_difficulty', .5))
    days = len(state.policy_data.get(f'{band}_recall_times', state.policy_data.get('recall_days', [])))
    stability = 1 + max(0, days - 1) * 0.3
    age = max(0, (now - occurred_at).total_seconds() / 86400)
    return 2 ** (-age / (base_half_life_days * stability))


@dataclass(frozen=True)
class ExponentialRetentionPolicy:
    version: str = 'retention-v3'
    base_half_life_days: float = 30

    def __post_init__(self):
        if not isfinite(self.base_half_life_days) or self.base_half_life_days <= 0:
            raise ValueError('Retention half-life must be positive and finite')

    def calculate(self, state: LearnerConceptState, now: datetime) -> float | None:
        anchor = state.last_demonstrated_at
        if anchor is None or state.retention_confidence is None:
            return None
        # One exam with twenty questions is not twenty spaced recall sessions.
        return state.retention_confidence * observation_freshness(state, anchor, now, self.base_half_life_days)
