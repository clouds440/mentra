from datetime import datetime
from typing import Protocol

from app.learner.models import LearnerConceptState, LearningEvidence


class MasteryPolicy(Protocol):
    version: str
    def update(self, state: LearnerConceptState, evidence: LearningEvidence) -> LearnerConceptState: ...


class ConfidencePolicy(Protocol):
    version: str
    def calculate(self, weight: float, variance: float, difficulty: float) -> float: ...


class RetentionPolicy(Protocol):
    version: str
    def calculate(self, state: LearnerConceptState, now: datetime) -> float | None: ...
