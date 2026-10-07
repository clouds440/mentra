from dataclasses import dataclass
from math import exp


@dataclass(frozen=True)
class HeuristicConfidencePolicy:
    version: str = 'confidence-v2'

    def calculate(self, weight: float, variance: float, difficulty: float) -> float:
        # Difficulty coverage is exposed separately; an easy failure can still be
        # a reliable observation of weakness. Consistency does not imply mastery.
        return min(0.95, (1 - exp(-weight / 4)) * (1 - min(0.6, variance * 2)))
