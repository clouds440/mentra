"""Deterministic provisional fit; never a mastery or causal-learning estimate."""
import hashlib,json
from math import isfinite

POLICY='challenge-fit-v1'
WINDOW=32
DAYS=90
STEP=.1

def scope_key(context_id,concept_id,language,answer_mode):
    return hashlib.sha256(json.dumps([context_id,concept_id,language,answer_mode],separators=(',',':')).encode()).hexdigest()

def evaluate(rows):
    if len(rows)>WINDOW:raise ValueError('Challenge policy window exceeded')
    harder=[row for row in rows if row['direction']=='harder']
    easier=[row for row in rows if row['direction']=='easier']
    supported=lambda group:len(group)>=3 and sum(row['items'] for row in group)>=6 and len({row['session'] for row in group})>=2
    mean=lambda group:sum(row['score'] for row in group)/len(group) if group else None
    if any(not isfinite(row['score']) or not 0<=row['score']<=1 for row in rows):raise ValueError('Invalid score')
    offset=0;flags=[]
    if supported(harder) and mean(harder)>=.8:
        offset=STEP
        if supported(easier) and mean(easier)<.5:flags.append('mixed_difficulty_results')
    elif supported(easier):
        offset=-STEP
        if mean(easier)<.5:flags.append('diagnostic_recommended')
    elif supported(harder) and mean(harder)<.5:flags.append('harder_not_yet_supported')
    return dict(offset=offset,families=len(rows),items=sum(row['items'] for row in rows),harder_families=len(harder),easier_families=len(easier),
        flags=flags,basis='provisional_observed_fit' if offset else 'insufficient_evidence',policy=POLICY)

def target(baseline,direction=None,offset=0):
    step=STEP if direction=='harder' else -STEP if direction=='easier' else offset
    return round(max(.1,min(.9,baseline+step)),3)
