"""Reproducible offline synthetic evaluation and persistent workflow verification.

Run with PYTHONPATH=backend and explicit TEST_DATABASE_URL. Uses an isolated PostgreSQL schema.
"""

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from app.learner import (
    LearnerEngine, EvidenceSubmissionRequest, ResolveLearningContextRequest,
    LearnerContextRequest, StudyRecommendationsRequest,
)
from app.learner.evaluation import evaluate_observations
from app.learner.repositories import PostgresLearnerRepository
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


def synthetic_trajectories(seed=47291, steps=150):
    """Labels come from separate latent ability curves, not the learner formula."""
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    learners = ('strong', 'novice', 'learning', 'regression', 'mixed', 'guided', 'easy-only', 'repeated-item')
    observations = []
    for index in range(steps):
        progress = index / max(1, steps - 1)
        for name in learners:
            ability = {'strong': 0.95, 'novice': 0.05, 'learning': 0.05 + 0.9 * progress,
                       'regression': 0.95 if progress < 0.65 else 0.05, 'mixed': 0.5,
                       'guided': 0.15, 'easy-only': 0.7, 'repeated-item': 0.5}[name]
            difficulty = 0.1 if name == 'easy-only' else (0.2, 0.5, 0.8)[index % 3]
            probability = 1 / (1 + math.exp(7 * (difficulty - ability)))
            assisted = name == 'guided'
            outcome = assisted or rng.random() < probability
            observations.append(EvidenceSubmissionRequest(
                learner_id=learner_id(name), concept_id='synthetic-concept', source_type='CHAT' if assisted else 'QUIZ',
                source_id=f'{name}:{index}', item_id='memorized' if name == 'repeated-item' else f'item:{index}',
                session_id=f'session:{index}', result='CORRECT' if outcome else 'INCORRECT',
                difficulty=difficulty, independence=0 if assisted else 1, hint_count=3 if assisted else 0,
                occurred_at=start + timedelta(hours=index),
            ))
    return observations


def verify(seed=47291, steps=150):
    observations = synthetic_trajectories(seed, steps)
    evaluation = evaluate_observations(observations)
    now = observations[-1].occurred_at
    labels = {learner_id(name): name for name in ('strong', 'novice', 'learning', 'regression', 'mixed', 'guided', 'easy-only', 'repeated-item')}
    with PostgresSandbox() as db:
        repository = db.repository
        engine = LearnerEngine(repository, clock=lambda: now)
        concept = engine.register_concept('Synthetic Skill')
        contexts = {name: engine.resolve_learning_context(ResolveLearningContextRequest(
            learner_id=name, name='Synthetic Subject', activate=True)).context_id
                    for name in sorted({r.learner_id for r in observations})}
        requests = [r.model_copy(update={'concept_id': concept.id, 'context_id': contexts[r.learner_id]})
                    for r in observations]
        begin = perf_counter()
        engine.submit_evidence_batch(requests)
        ingest_seconds = perf_counter() - begin
        # Restart through a fresh adapter/engine rather than relying on objects in memory.
        engine = LearnerEngine(PostgresLearnerRepository(db.sessions), clock=lambda: now)
        states, retrieval = {}, {}
        for name in contexts:
            before = repository.get_state(name, concept.id)
            after = engine.recompute_learner_state(name, concept.id)
            if before.policy_data != after.policy_data or before.mastery != after.mastery:
                raise AssertionError(f'Replay diverged for {name}')
            begin = perf_counter()
            connections_before = db.connections
            packet = engine.get_relevant_context(LearnerContextRequest(learner_id=name, query='Synthetic Skill'))
            recommendations = engine.get_study_recommendations(StudyRecommendationsRequest(learner_id=name))
            if packet.context_ids != [contexts[name]] or len(recommendations) != 1:
                raise AssertionError(f'Context isolation failed for {name}')
            if labels.get(name) == 'guided' and after.mastery is not None:
                raise AssertionError('Guided practice manufactured mastery')
            if labels.get(name) == 'repeated-item' and len(after.policy_data.get('independent_items', [])) > 1:
                raise AssertionError('Repetition manufactured item diversity')
            states[labels[name]] = engine.states.response(after).model_dump(mode='json')
            retrieval[labels[name]] = dict(milliseconds=(perf_counter() - begin) * 1000,
                                   connections=db.connections - connections_before,
                                   packet_bytes=len(packet.model_dump_json(exclude_none=True).encode()))
    return dict(kind='synthetic behavioral evaluation; not measured real-world accuracy', seed=seed,
                observations=len(observations), evaluation=evaluation, states=states,
                performance=dict(ingestion_seconds=ingest_seconds,
                                 observations_per_second=len(observations) / ingest_seconds,
                                 retrieval=retrieval), restart_replay_equal=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seed', type=int, default=47291)
    args = parser.parse_args()
    report = verify(args.seed)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['kind', 'observations', 'restart_replay_equal']} |
                     {'evaluation': {k: v for k, v in report['evaluation'].items() if k != 'groups'}}, indent=2))
