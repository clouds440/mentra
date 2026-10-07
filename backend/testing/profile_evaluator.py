"""Predictable AI test double. Production always uses LangChainProfileEvaluator."""
from app.student_profile.schemas import AIEvaluation, Candidate, DIMENSIONS
from app.student_profile.policy import dimension_items
from app.student_profile.errors import EvaluationUnavailable


class UnavailableTestProfileEvaluator:
    async def evaluate(self, *_):
        raise EvaluationUnavailable('Simulated provider outage')


class TestProfileEvaluator:
    def __init__(self):
        self.calls = []

    async def evaluate(self, evidence, context):
        self.calls.append((evidence, context))
        result = {}
        for dimension in DIMENSIONS:
            items = dimension_items(evidence, dimension)
            result[dimension] = Candidate(value=(sum(item.correct for item in items) + 1) / (len(items) + 2) if items else None,
                confidence=.5 if items else 0, evidence_ids=[item.id for item in items], rationale='Provisional result from the supplied scored items.' if items else 'No evidence supplied.')
        return AIEvaluation(**result)
