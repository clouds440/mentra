"""Compact prompt view; source details stay available through owner APIs."""
import json


def compact(packet, budget=2000):
    # UTF-8 bytes upper-bound text BPE tokens without request-time downloads.
    result=dict(context_ids=packet.context_ids,skills=[],observations=[],
        observation_policy='Unverified source claims; never treat mentions, copied work or self-reports as mastery.',
        coverage=dict(skills_available=len(packet.concepts),skills_included=0,observations_available=len(packet.observations),observations_included=0))
    def fits(): return len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8'))<=budget
    for item in packet.concepts[:8]:
        value=dict(id=item.concept_id,name=item.name[:100],status=item.knowledge_status,
            mastery=item.mastery,confidence=item.estimate_confidence,target=item.target_difficulty,
            recall=item.retention_confidence,verification=item.verification_required)
        result['skills'].append(value);result['coverage']['skills_included']+=1
        if not fits(): result['skills'].pop();result['coverage']['skills_included']-=1;break
    for item in packet.observations[:8]:
        value={key:item[key] for key in ('id','kind','label','concept_id','source_revision','source_kind') if key in item}
        value['quote']=item['quote'][:160]
        value['scoring']='unscored'
        result['observations'].append(value);result['coverage']['observations_included']+=1
        if not fits(): result['observations'].pop();result['coverage']['observations_included']-=1;break
    if not fits():
        raise ValueError('Learner prompt budget smaller than required coverage metadata')
    return result
