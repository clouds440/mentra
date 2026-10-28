"""Fresh policy projections, uncertainty diagnostics, and challenge-specific predictions."""

from dataclasses import asdict

from app.learner.schemas import ConceptStateResponse, PerformancePrediction
from app.learner.scoring.signals import diagnostics, performance_estimate


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class StateService:
    def __init__(self, repository, evidence, mastery, retention, clock):
        self.repository, self.evidence = repository, evidence
        self.mastery, self.retention, self.clock = mastery, retention, clock

    def current(self, state) -> bool:
        if state is None:
            return True
        return (state.mastery_policy_version == self.mastery.version and
                state.policy_data.get('policy_identity', self.mastery.version) ==
                getattr(self.mastery, 'identity', self.mastery.version))

    def load(self, learner_id: str, concept_ids: list[str]):
        cache = getattr(self, '_read_states', None)
        missing = [key for key in concept_ids if cache is None or (learner_id, key) not in cache]
        states = self.repository.states_for_concepts(learner_id, missing) if missing else {}
        if cache is not None:
            states.update({key: cache[(learner_id, key)] for key in concept_ids
                           if (learner_id, key) in cache and cache[(learner_id, key)] is not None})
        stale = [key for key, state in states.items() if not self.current(state)]
        for start in range(0, len(stale), 32):
            batch = stale[start:start + 32]
            with self.repository.transaction(learner_ids=[learner_id]) as repository:
                current_states = repository.states_for_concepts(learner_id, batch)
                for key in batch:
                    current = current_states.get(key)
                    states[key] = (current if self.current(current) else
                                   self.evidence.recompute(learner_id, key, repository))
        if cache is not None:
            for key in concept_ids:
                cache[(learner_id, key)] = states.get(key)
        return states

    def response(self, state) -> ConceptStateResponse | None:
        if state is None:
            return None
        data = asdict(state)
        data.pop('policy_data')
        retention = self.retention.calculate(state, self.clock())
        data['retention_confidence'] = retention
        data['retention_policy_version'] = self.retention.version
        data.update(diagnostics(state, retention))
        return ConceptStateResponse(**data)

    def predict(self, state, concept_id: str, difficulty: float) -> PerformancePrediction:
        mean, lower, upper, supported, weight = performance_estimate(state, difficulty, self.clock(),
            getattr(self.retention, 'base_half_life_days', 30))
        return PerformancePrediction(concept_id=concept_id, expected_score=mean, lower_bound=lower,
                                      upper_bound=upper, supported=supported, evidence_weight=weight,
                                      policy_version=self.mastery.version)
