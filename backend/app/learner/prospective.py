"""Predeclared prospective holdout evaluation, never a belief mutation."""
from collections import Counter,defaultdict
from datetime import datetime
from math import isfinite
from random import Random
from app.learner.evaluation import Prediction,evaluate_predictions


def evaluate(rows, protocol, *, resamples=2000):
    if resamples<200:raise ValueError('At least 200 cluster bootstrap resamples required')
    registered=datetime.fromisoformat(protocol['registered_at']);cutoff=datetime.fromisoformat(protocol['holdout_after'])
    if registered>cutoff:raise ValueError('Protocol must precede holdout collection')
    train_students=set(protocol['training_students']);train_families=set(protocol['training_item_families'])
    seen=set();accepted=[];excluded=Counter()
    previous=None
    for row in rows:
        at=datetime.fromisoformat(row['captured_at']);outcome_at=datetime.fromisoformat(row['outcome_at'])
        if previous and at<previous:raise ValueError('Records must be chronological')
        previous=at
        identity=(row['student'],row['attempt_id'],row['question_id'])
        if identity in seen:raise ValueError('Duplicate statistical unit')
        seen.add(identity)
        if at>=outcome_at:raise ValueError('Outcome leakage: prediction was not made before outcome')
        if row['student'] in train_students or row['item_family'] in train_families:raise ValueError('Holdout overlaps training groups')
        for key in ('expected_score','baseline_recent','baseline_band','observed'):
            if not isfinite(row[key]) or not 0<=row[key]<=1:raise ValueError('Invalid probability/outcome')
        reason=('pre_protocol' if at<=cutoff else 'synthetic' if row.get('synthetic',True) else
            'unsupported' if not row['supported'] else 'repeat' if not row['first_exposure'] else
            'assistance' if row['assistance']!='independent' else 'unreviewed' if not row.get('independently_reviewed') else
            'invalidated' if not row['valid'] else None)
        if reason:excluded[reason]+=1;continue
        accepted.append(row)
    if not accepted:return dict(status='held',count=0,excluded=dict(excluded),reason='No qualified prospective outcomes')
    students=sorted({r['student'] for r in accepted});families=sorted({r['item_family'] for r in accepted})
    def brier(data,key,weights=None):
        weights=weights or [1]*len(data)
        total=sum(weights)
        return sum(w*(r[key]-r['observed'])**2 for r,w in zip(data,weights))/total if total else None
    model=brier(accepted,'expected_score');rng=Random(71937);baselines={}
    for key in ('baseline_recent','baseline_band'):
        baseline=brier(accepted,key);gains=[]
        for _ in range(resamples):
            # Paired two-way cluster weights retain student and repeated-family dependence.
            sw=Counter(rng.choices(students,k=len(students)));fw=Counter(rng.choices(families,k=len(families)))
            weights=[sw[r['student']]*fw[r['item_family']] for r in accepted]
            b=brier(accepted,key,weights);m=brier(accepted,'expected_score',weights)
            if b:gains.append((b-m)/b)
        gains.sort();lo=gains[int(.025*len(gains))] if gains else -1;hi=gains[min(len(gains)-1,int(.975*len(gains)))] if gains else -1
        gain=(baseline-model)/baseline if baseline else -1
        baselines[key]=dict(brier=baseline,relative_gain=gain,ci95=[lo,hi],passed=gain>=.1 and lo>0)
    calibration=evaluate_predictions([Prediction(r['expected_score'],r['observed']) for r in accepted])['calibration_error']
    subgroups=defaultdict(list)
    for row in accepted:
        for key in ('language','answer_mode'):
            subgroups[f'{key}:{row[key]}'].append(row)
    subgroup_results={name:dict(count=len(values),no_harm=all(brier(values,'expected_score')<=brier(values,key)+.02 for key in baselines)) for name,values in subgroups.items()}
    coverage=(len(accepted)>=protocol['minimum_outcomes'] and len(students)>=protocol['minimum_students'] and len(families)>=protocol['minimum_families']
        and all(result['count']>=protocol['minimum_subgroup'] for result in subgroup_results.values())
        and set(protocol['required_subgroups']).issubset(subgroup_results))
    passed=coverage and calibration<=.05 and all(r['passed'] for r in baselines.values()) and all(r['no_harm'] for r in subgroup_results.values())
    return dict(status='passed' if passed else 'held',count=len(accepted),total_records=len(rows),support_coverage=len(accepted)/len(rows),students=len(students),families=len(families),brier=model,
        ece=calibration,baselines=baselines,subgroups=subgroup_results,coverage_passed=coverage,excluded=dict(excluded),
        protocol='prospective-v1',limitations='Human provenance and semantic family grouping require independent adjudication; this tool cannot certify them.')


def blinded_ablation(cases, seed):
    """Same task/source, learner packet on/off. Arm map is private to the operator."""
    from copy import deepcopy
    from hashlib import sha256
    rng=Random(seed);public=[];arms={}
    for case in cases:
        pair=[]
        for personalized in (False,True):
            value=deepcopy(case);identifier=sha256(f"{seed}:{case['id']}:{personalized}".encode()).hexdigest()
            value['id']=identifier
            if not personalized:value['learner_context']=None
            arms[identifier]=dict(case_id=case['id'],personalized=personalized);pair.append(value)
        rng.shuffle(pair);public.extend(pair)
    rng.shuffle(public)
    return dict(cases=public,private_arms=arms)
