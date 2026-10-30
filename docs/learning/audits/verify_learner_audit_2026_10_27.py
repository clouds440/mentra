"""Historical pre-implementation probes for the 2026-10-27 audit.

The recorded JSON describes the original behavior, not current acceptance criteria.
Use backend/tests/learner and the verify_* release scripts for current checks.
No DB/provider calls.
"""
import json
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.learner.models import LearnerConceptState, LearningEvidence
from app.learner.scoring.mastery import HeuristicMasteryPolicy
from app.learner.scoring.retention import ExponentialRetentionPolicy
from app.learner.scoring.signals import diagnostics, performance_estimate
from app.learner.ranking import WeightedRankingPolicy
from app.langchain.planning import plan_request
from app.langchain.assessment_workflows import AssessmentWorkflows

now = datetime(2026, 10, 27, tzinfo=timezone.utc)
policy = HeuristicMasteryPolicy()
retention = ExponentialRetentionPolicy()

def answer(state, serial, *, when=now, difficulty=.8, result='CORRECT', channel='QUIZ'):
    return policy.update(state, LearningEvidence(
        id=str(serial), learner_id='audit', concept_id='concept', source_type=channel,
        source_id=str(serial), item_id=str(serial), session_id=str(serial),
        occurred_at=when, result=result, difficulty=difficulty, independence=1,
        evidence_confidence=1))

state = LearnerConceptState('audit', 'concept')
for i in range(10):
    state = answer(state, i)
curve = {str(day): round(retention.calculate(state, now+timedelta(days=day)), 6)
         for day in (0, 7, 30, 60, 90)}
assert curve['0'] > curve['30'] > curve['60']
assert retention.calculate(LearnerConceptState('audit', 'concept'), now) is None

spaced = LearnerConceptState('audit', 'concept')
for i in range(10):
    spaced = answer(spaced, i, when=now-timedelta(days=9-i))
assert retention.calculate(spaced, now+timedelta(days=30)) > curve['30']

routes = {}
for query in ('Explain transitive dependency', 'What should I study next?',
              'Mujhe agla kya parhna chahiye?', 'I keep confusing joins and subqueries'):
    plan = plan_request(query)
    routes[query] = dict(modules=[step.module for step in plan.steps], direct=plan.direct_candidate)
assert 'learner' not in routes['Explain transitive dependency']['modules']
assert 'learner' in routes['What should I study next?']['modules']

# Recent low-quality independent failure updates prediction-band freshness, while
# successful retention remains anchored at the earlier demonstration.
old = state
failure = answer(old, 'late-failure', when=now+timedelta(days=90), result='INCORRECT', channel='CHAT')
before_prediction = performance_estimate(old, .8, now+timedelta(days=90))
after_prediction = performance_estimate(failure, .8, now+timedelta(days=90))
assert after_prediction[0] > before_prediction[0]
assert diagnostics(state, curve['30'])['knowledge_status'] == 'needs_verification'

ranking = WeightedRankingPolicy()
scores = {}
for relevance in (.5, 1):
    base, reason = ranking.score(state, .7, 0, relevance)
    scores[str(relevance)] = dict(base=base, final=base*.6*(.5+.5*relevance), reason=reason)
assert scores['1']['final'] > scores['0.5']['final']

async def mcq_probe():
    question = dict(id='q', options=[dict(id='a', label='A'), dict(id='b', label='B')],
        correct_option_id='a', correct_option_ids=['a'], marks=1,
        concept_ids=['fractions', 'algebra'], model_answer='Answer a')
    grade = await AssessmentWorkflows(None, None).grade(dict(assessment=dict(questions=[question]),
        attempt=dict(answers={'q': 'a'})))
    return grade.model_dump(mode='json')

result = dict(
    scope='Pure domain probes; no PostgreSQL, browser, or live model verification.',
    retention_curve_same_day_10_successes=curve,
    retention_after_30_days_spaced_10_successes=retention.calculate(spaced, now+timedelta(days=30)),
    mastery_before_and_after_elapsed_time=[state.mastery, state.mastery],
    status_now=diagnostics(state, retention.calculate(state, now)),
    status_after_30_days=diagnostics(state, retention.calculate(state, now+timedelta(days=30))),
    routes=routes, relevance_scores=scores,
    prediction_before_late_chat_failure=before_prediction,
    prediction_after_late_chat_failure=after_prediction,
    retention_after_late_chat_failure=retention.calculate(failure, now+timedelta(days=90)),
    multi_concept_mcq=None)
# The Windows runtime cannot create the local sockets used by an asyncio loop
# under this execution profile. This MCQ-only path has no pending model tasks;
# drive the coroutine directly with empty task coordination patched explicitly.
async def empty_gather(*args, **kwargs):
    return []
with patch('asyncio.as_completed', return_value=[]), patch('asyncio.gather', empty_gather):
    probe = mcq_probe()
    try:
        probe.send(None)
        raise AssertionError('MCQ probe unexpectedly awaited external work')
    except StopIteration as completed:
        result['multi_concept_mcq'] = completed.value
components = result['multi_concept_mcq']['questions'][0]['concept_grades']
assert set(components) == {'fractions', 'algebra'}
assert all(value['score'] == 1 and value['confidence'] == 1 for value in components.values())
target = Path('docs/learning/verification/learner-audit-domain-probes-2026-10-27.json')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
