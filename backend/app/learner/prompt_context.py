"""Compact prompt view; source details stay available through owner APIs."""
import json


def compact(packet, budget=2000):
    # UTF-8 bytes upper-bound text BPE tokens without request-time downloads.
    result=dict(context_ids=packet.context_ids,skills=[],observations=[],
        observation_policy='Unverified source claims; never treat mentions, copied work or self-reports as mastery.',
        coverage=dict(skills_available=len(packet.concepts),skills_included=0,observations_available=len(packet.observations),observations_included=0))
    def fits(): return len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8'))<=budget
    def observation(item):
        value={key:item[key] for key in ('id','kind','concept_id','source_revision','source_kind','context_id') if key in item}
        value.update(label=item.get('label','')[:80],topic=item.get('topic','')[:80],quote=item['quote'][:160],scoring='unscored')
        return value
    # Reserve a source-backed encounter/struggle before a scored skill list can
    # consume the whole packet. Full observations remain in the owned source API.
    if packet.observations:
        result['observations'].append(observation(packet.observations[0]));result['coverage']['observations_included']=1
        if not fits():result['observations'].pop();result['coverage']['observations_included']=0
    number=lambda value:round(value,3) if value is not None else None
    for item in packet.concepts[:8]:
        value=dict(id=item.concept_id,name=item.name[:100],status=item.knowledge_status,
            mastery=number(item.mastery),confidence=number(item.estimate_confidence),target=number(item.target_difficulty),
            recall=number(item.retention_confidence),verification=item.verification_required,
            importance=number(item.importance),relevance=number(item.relevance),independent_items=item.independent_item_count,
            target_supported=bool(item.target_performance and item.target_performance.supported),
            misconceptions=[text[:120] for text in item.misconceptions[:1]])
        result['skills'].append(value);result['coverage']['skills_included']+=1
        if not fits(): result['skills'].pop();result['coverage']['skills_included']-=1;break
    for item in packet.observations[result['coverage']['observations_included']:8]:
        value=observation(item)
        result['observations'].append(value);result['coverage']['observations_included']+=1
        if not fits(): result['observations'].pop();result['coverage']['observations_included']-=1;break
    if not fits():
        raise ValueError('Learner prompt budget smaller than required coverage metadata')
    return result
