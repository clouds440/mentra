"""Private immutable pre-outcome records; never part of a public handoff."""
from hashlib import sha256
import json
import unicodedata
from datetime import datetime
from sqlalchemy import select, literal, union_all
from app.learner.repositories.tables import learner_concept_state
from app.learner.repositories.postgres_parts.base import PostgresRepositoryBase
from app.learner.scoring.projection import project, expected
from app.learner.scoring.signals import difficulty_band
from app.learner.scoring import HeuristicMasteryPolicy,ExponentialRetentionPolicy
from .tables import prediction_snapshots as snapshots


def content_hash(question):
    # Exclude generated IDs and keys. Exact copies with reordered options share exposure.
    text=lambda value:' '.join(unicodedata.normalize('NFKC',str(value)).casefold().split())
    value=[text(question['prompt']),text(question.get('context','')),
        sorted(text(option['label']) for option in question.get('options',[]))]
    return sha256(json.dumps(value,ensure_ascii=False).encode()).hexdigest()


def capture(session, owner, assessment, attempt, now):
    questions=assessment['questions']
    ids={identifier for q in questions for identifier in q['concept_ids']}
    # This is one bounded read in the existing owner transaction, never a ledger scan.
    states={row['concept_id']:PostgresRepositoryBase._state_from_row(row) for row in session.execute(
        select(learner_concept_state).where(learner_concept_state.c.learner_id==owner,
            learner_concept_state.c.concept_id.in_(ids)).limit(256)).mappings()}
    lineage=assessment.get('practice_lineage') or {}
    families={q['id']:lineage.get('question_items',{}).get(q['id'],f"{assessment['id']}:{q['id']}") for q in questions}
    hashes={q['id']:content_hash(q) for q in questions}
    # Return one boolean pair per question, even after years of repeated exposure.
    exposure={row[0]:(row[1] or row[2]) for row in session.execute(union_all(*[
        select(literal(q['id']),select(snapshots.c.attempt_id).where(snapshots.c.learner_id==owner,
            snapshots.c.item_family==families[q['id']]).exists(),
            select(snapshots.c.attempt_id).where(snapshots.c.learner_id==owner,
                snapshots.c.content_hash==hashes[q['id']]).exists()) for q in questions]))}
    current_hashes=set()
    rows=[]
    for q in questions:
        predicted=[];recent=[];band_values=[];versions={};policies=set();supported=bool(q['concept_ids'])
        for identifier in q['concept_ids']:
            state=states.get(identifier);p=.5;ok=False;b=.5;r=.5
            if state:
                versions[identifier]=state.version
                data=state.policy_data;half_life=data.get('ranking_half_life')
                current=(state.mastery_policy_version==HeuristicMasteryPolicy.version and
                    data.get('policy_identity')==HeuristicMasteryPolicy().identity and
                    state.retention_policy_version==ExponentialRetentionPolicy.version)
                projection=project(state,half_life) if half_life and current else None
                if projection and projection['anchor']<=now:
                    p,ok=expected(projection,q['difficulty'],now)
                    band=difficulty_band(q['difficulty'])
                    b=(.5+data.get(f'{band}_success',0))/(1+data.get(f'{band}_weight',0))
                    observations=sorted((row for name in ('easy','medium','hard') for row in data.get(f'{name}_observations',[])
                        if datetime.fromisoformat(row['at'])<=now),key=lambda row:datetime.fromisoformat(row['at']))[-5:]
                    r=(.5+sum(row['outcome'] for row in observations))/(1+len(observations))
                    policies.add(projection['policy_identity'])
            predicted.append(p);recent.append(r);band_values.append(b);supported&=ok
        mean=lambda values:sum(values)/len(values) if values else .5
        rows.append(dict(learner_id=owner,attempt_id=attempt['id'],question_id=q['id'],captured_at=now,
            item_family=families[q['id']],content_hash=hashes[q['id']],
            first_exposure=attempt['attempt_number']==1 and not lineage and not exposure[q['id']] and hashes[q['id']] not in current_hashes,
            expected_score=mean(predicted),supported=supported,baseline_recent=mean(recent),baseline_band=mean(band_values),
            state_versions=versions,policy_identity=sorted(policies),assessment_revision=assessment['revision'],
            protocol='prospective-v1',answer_mode=q.get('answer_mode','text')))
        current_hashes.add(hashes[q['id']])
    if rows:session.execute(snapshots.insert(),rows)
