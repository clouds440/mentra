"""Reproducible quality release gates; empty/unreviewed corpora never pass."""
import math
from collections import Counter

ASPECTS=('alignment','solvability','clarity','level')
SEVERE={'wrong_key','contradictory_rubric','answer_leak'}


def quality_gate(items):
    counts=Counter(); valid=[]; defects=[]; invalid=[]; seen=set(); hashes=set()
    for item in items:
        identifier=item['id']
        source_hash=item.get('source_hash')
        if identifier in seen or not source_hash or source_hash in hashes:
            invalid.append(identifier); continue
        seen.add(identifier); hashes.add(source_hash)
        reviews=item.get('reviews',[])
        reviewers={review.get('reviewer_id') for review in reviews}
        independent=(len(reviews)==2 and len(reviewers)==2 and None not in reviewers
            and all(review.get('method')=='independent_human' and review.get('blinded') is True for review in reviews)
            and item.get('generator_id') not in reviewers)
        resolved=item.get('adjudication') or {}
        ratings=resolved.get('ratings') or {}
        disagreement=bool(len(reviews)==2 and (reviews[0].get('ratings')!=reviews[1].get('ratings') or reviews[0].get('defects')!=reviews[1].get('defects')
            or ratings!=reviews[0].get('ratings') or resolved.get('defects')!=reviews[0].get('defects')))
        adjudicated=(resolved.get('accepted') is True and all(type(ratings.get(key)) is int and 1<=ratings[key]<=5 for key in ASPECTS)
            and (not disagreement or resolved.get('reviewer_id') not in reviewers|{None}))
        if not independent or not adjudicated or item.get('language') not in ('en','ar'):
            invalid.append(identifier); continue
        counts[item['language']]+=1
        severe=set(resolved.get('defects',[])) & SEVERE
        if severe: defects.append(identifier)
        valid.append((item,all(ratings[key]>=4 for key in ASPECTS)))
    groups={}
    for item,passes in valid:
        for key in (f"language:{item['language']}",f"format:{item.get('format','unknown')}"):
            total,good=groups.get(key,(0,0));groups[key]=(total+1,good+int(passes))
    quality=sum(passes for _,passes in valid)/len(valid) if valid else 0
    correctness=counts['en']>=300 and counts['ar']>=300 and not defects and not invalid
    subgroup=all(good/total>=.9 for total,good in groups.values())
    return dict(policy='assessment-quality-gates-v1',reviewed=len(valid),counts=dict(counts),
        severe_defects=defects,unqualified_reviews=invalid,quality_fraction=quality,
        groups={key:dict(count=total,fraction=good/total) for key,(total,good) in groups.items()},
        zero_defect_upper_95=1-math.pow(.05,1/len(valid)) if valid and not defects else None,
        G8=correctness,G9_items=bool(correctness and quality>=.95 and subgroup),
        decision='promote' if correctness and quality>=.95 and subgroup else 'hold_reviewed_item_fallback')


def grading_gate(pairs):
    if not pairs: return dict(passed=False,count=0,reason='no_adjudicated_grades')
    values=[]
    for item in pairs:
        maximum=item['max_score']
        if maximum<=0 or not 0<=item['model_score']<=maximum or not 0<=item['adjudicated_score']<=maximum:
            raise ValueError('Grade outside rubric scale')
        values.append((item['model_score']/maximum,item['adjudicated_score']/maximum))
    mae=sum(abs(a-b) for a,b in values)/len(values)
    # Quadratic weighted kappa on predeclared five grade bands; preserve raw
    # normalized MAE as well so banding cannot conceal boundary errors.
    bins=[(min(4,int(a*4+.5)),min(4,int(b*4+.5))) for a,b in values]
    left=Counter(a for a,_ in bins);right=Counter(b for _,b in bins)
    observed=sum(((a-b)/4)**2 for a,b in bins)/len(bins)
    expected=sum(left[a]*right[b]*((a-b)/4)**2 for a in range(5) for b in range(5))/len(bins)**2
    kappa=1-observed/expected if expected else None
    return dict(count=len(values),normalized_mae=mae,weighted_kappa=kappa,
        passed=bool(kappa is not None and kappa>=.8 and mae<=.10))
