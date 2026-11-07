"""Exact explicit choices win; learned targets stay skill/language/format scoped."""
from app.core.config import settings
from .policy import target


def planning_targets(request,revision,plan,packet):
    targets=[]
    if request.challenge_direction and revision:
        for index,(entry,original) in enumerate(zip(plan,revision['questions'])):
            step=.1 if request.challenge_direction=='harder' else -.1
            entry['difficulty_target']=round(max(0,min(1,original['difficulty']+step)),3)
            entry['challenge_reason']='explicit_user_choice'
            if len(original['concept_ids'])==1:entry['target_subskill_id']=original['concept_ids'][0]
            entry['required_subskill_ids']=list(original['concept_ids'])
        return targets
    if not packet or not settings.learner_challenge_adaptation_enabled or not settings.learner_personalization_enabled:
        return targets
    for item in packet.concepts:
        for preference in item.challenge_preferences:
            if preference['context_id']==request.context_id and (request.language=='und' or preference['language']==request.language):
                targets.append(dict(concept_id=item.concept_id,language=preference['language'],answer_mode=preference['answer_mode'],
                    difficulty_target=target(item.target_difficulty,offset=preference['offset']),
                    support_families=preference['families'],basis='provisional_practice_fit'))
    return targets[:16]
