"""Independent labeled-turn gate; development fixtures cannot qualify release."""
from collections import Counter

KINDS={'encounter','struggle','self_report','guided_work','demonstration'}


def signal_gate(records):
    true_positive=false_positive=false_negative=0
    reviewed=0;invalid=[];mastery_violations=[];seen=set();hashes=set()
    strata={};kind_counts=Counter();language_counts=Counter()
    for record in records:
        identifier=record['id'];review=record.get('review') or {}
        if (identifier in seen or not record.get('source_hash') or record['source_hash'] in hashes
                or review.get('method')!='independent_human' or not review.get('reviewer_id')
                or review.get('adjudicated') is not True):
            invalid.append(identifier);continue
        seen.add(identifier);hashes.add(record['source_hash']);reviewed+=1
        gold={item['id']:item for item in record.get('gold',[])}
        matched=set();tp=fp=0
        for prediction in record.get('predictions',[]):
            if prediction.get('claims_mastery') or any(key in prediction for key in ('mastery','score','independent_success')):
                mastery_violations.append(identifier)
            match=prediction.get('matched_gold_id');expected=gold.get(match)
            valid=(prediction.get('adjudicated_match') is True and expected is not None and match not in matched
                and prediction.get('kind')==expected['kind'] and prediction.get('source_id')==expected['source_id'])
            if valid:matched.add(match);tp+=1
            else:fp+=1
        fn=len(gold)-len(matched)
        true_positive+=tp;false_positive+=fp;false_negative+=fn
        language=record.get('language','unknown');language_counts[language]+=len(gold)
        for name in (f'language:{language}',):
            correct,total=strata.get(name,(0,0));strata[name]=(correct+tp,total+len(gold))
        for expected in gold.values():
            kind=expected['kind'];kind_counts[kind]+=1
            name=f'kind:{kind}';correct,total=strata.get(name,(0,0))
            strata[name]=(correct+int(expected['id'] in matched),total+1)
    precision=true_positive/(true_positive+false_positive) if true_positive+false_positive else None
    recall=true_positive/(true_positive+false_negative) if true_positive+false_negative else None
    subgroup={key:dict(correct=good,total=total,recall=good/total if total else None) for key,(good,total) in strata.items()}
    coverage=all(kind_counts[kind]>=10 for kind in KINDS) and all(language_counts[language]>=30 for language in ('en','ar'))
    passed=bool(reviewed>=300 and not invalid and not mastery_violations and coverage
        and precision is not None and precision>=.95 and recall is not None and recall>=.90
        and all(item['recall']>=.85 for item in subgroup.values() if item['recall'] is not None))
    return dict(policy='learning-signal-evaluation-v1',reviewed_turns=reviewed,unqualified=invalid,
        true_positive=true_positive,false_positive=false_positive,false_negative=false_negative,
        precision=precision,recall=recall,strata=subgroup,mastery_violations=mastery_violations,
        coverage_qualified=coverage,G10=passed,
        decision='eligible_for_capture_promotion' if passed else 'hold_unscored_observations_only')
