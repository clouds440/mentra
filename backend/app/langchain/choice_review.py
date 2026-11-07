"""Key derivation and bounded semantic checks before choice/revision publication."""
import hashlib,json
from math import ceil
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from .prompts import PromptSource
from .generation_recovery import GenerationMismatch
from app.core.logging import workflow_logger


class ChoiceReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    position:int=Field(ge=1)
    answer_ids:list[str]=Field(max_length=6)
    answerable:bool
    explanation_valid:bool
    scope_preserved:bool
    requested_change_met:bool
    change_kind:Literal['reasoning_steps','scaffolding','representation_transfer','unchanged','not_requested']='not_requested'
    change_basis:str=Field(default='',max_length=800)
    problem_detail:str=Field(default='',max_length=1600)
    confidence:float=Field(ge=0,le=1)
    reason_code:Literal['ok','incorrect_or_missing_options','ambiguous','wrong_explanation','wrong_scope','unchanged_challenge','uncertain']

class ChoiceReviewBatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items:list[ChoiceReview]=Field(min_length=1,max_length=6)


class IndependentSolution(BaseModel):
    model_config=ConfigDict(extra='forbid')
    position:int=Field(ge=1)
    answer_ids:list[str]=Field(max_length=6)
    answerable:bool
    solution:str=Field(max_length=1600)
    confidence:float=Field(ge=0,le=1)
    problem_detail:str=Field(default='',max_length=1600)


class IndependentSolutionBatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items:list[IndependentSolution]=Field(min_length=1,max_length=6)


class ChoiceReviewer:
    def __init__(self,llm):self.llm,self.accepted,self.solutions=llm,{},{}

    async def _call(self,payload,schema):
        from pydantic import ValidationError
        from langchain_core.exceptions import OutputParserException
        from app.core.exceptions import AppError
        positions=[q['position'] for q in payload['questions']]
        local_questions=[]
        for number,q in enumerate(payload['questions'],1):
            item=dict(q,position=number)
            if 'independent_solution' in item:item['independent_solution']=dict(item['independent_solution'],position=number)
            local_questions.append(item)
        local_payload=dict(payload,questions=local_questions)
        for attempt in range(2):
            try:
                result=await self.llm.ainvoke(PromptSource.ASSESSMENT_CHOICE_REVIEW,local_payload,
                    system_context='Return only a JSON object matching this schema: '+json.dumps(schema.model_json_schema(),separators=(',',':')),
                    output_schema=schema)
                expected=set(range(1,len(positions)+1))
                if len(result.items)!=len(expected) or {q.position for q in result.items}!=expected:
                    raise ValueError('incomplete_review')
                return result.model_copy(update={'items':[item.model_copy(update={'position':positions[item.position-1]}) for item in result.items]})
            except (ValueError,ValidationError,OutputParserException):
                if attempt:raise AppError('ASSESSMENT_REVIEW_UNAVAILABLE','The assessment check could not finish. Please retry.',503) from None

    async def verify(self,questions,*,topic,direction=None,originals=None,skills=None):
        pending=[]
        for index,q in enumerate(questions):
            if not q.options and not direction:continue
            original=(originals or [])[index] if originals and index<len(originals) else None
            public_original={key:original.get(key) for key in ('prompt','context','options')} if original else None
            if public_original is not None and skills:
                public_original['assessed_skills']=[item['name'] for item in skills if item['id'] in original.get('concept_ids',[])]
            semantic=q.model_dump(mode='json',include={'prompt','context','answer_mode','options','model_answer','rubric','correct_option_id','correct_option_ids'})
            identity=json.dumps(dict(question=semantic,topic=topic,direction=direction,
                original=public_original),sort_keys=True,ensure_ascii=False,default=str)
            signature=hashlib.sha256(identity.encode()).hexdigest()
            if signature in self.accepted:
                q._choice_reviewed=True;q._challenge_change_verified=self.accepted[signature];continue
            q._choice_reviewed=False;q._challenge_change_verified=False
            public=dict(position=index+1,prompt=q.prompt,context=q.context,answer_mode=q.answer_mode,
                options=[o.model_dump() for o in q.options],explanation=q.model_answer,rubric=q.rubric)
            if original:public['original']=public_original
            pending.append((index,q,signature,public))
        invalid=[];problems=[]
        for offset in range(0,len(pending),6):
            batch=pending[offset:offset+6]
            from .assessment_reference import REFERENCE,word_facts
            facts=word_facts(json.dumps([row[3] for row in batch],ensure_ascii=False))
            independent={}
            if direction and any(not q.options for _,q,_,_ in batch):
                unseen=[]
                for index,q,_,public in batch:
                    blind={k:public[k] for k in ('position','prompt','context','answer_mode','options')}
                    identity=json.dumps({k:v for k,v in blind.items() if k!='position'},sort_keys=True,ensure_ascii=False)
                    if identity in self.solutions:
                        independent[index+1]=self.solutions[identity].model_copy(update={'position':index+1})
                    else:unseen.append((identity,blind))
                if unseen:
                    blind_questions=[row[1] for row in unseen]
                    blind_facts=word_facts(json.dumps(blind_questions,ensure_ascii=False))
                    solved=await self._call(dict(stage='independently_solve',topic=topic,questions=blind_questions,
                        orthography_reference=REFERENCE if blind_facts else '',word_facts=blind_facts),IndependentSolutionBatch)
                    if len(solved.items)!=len(unseen) or {q.position for q in solved.items}!={q['position'] for _,q in unseen}:
                        from app.core.exceptions import AppError
                        raise AppError('ASSESSMENT_REVIEW_UNAVAILABLE','The assessment check was incomplete. Please retry.',503)
                    for identity,blind in unseen:
                        solution=next(item for item in solved.items if item.position==blind['position'])
                        self.solutions[identity]=solution;independent[solution.position]=solution
                for _,_,_,public in batch:public['independent_solution']=independent[public['position']].model_dump()
            result=await self._call(dict(stage='check_solution_and_change',topic=topic,direction=direction,
                questions=[row[3] for row in batch],**(dict(orthography_reference=REFERENCE,word_facts=facts) if facts else {})),ChoiceReviewBatch)
            expected={row[0]+1 for row in batch}
            if len(result.items)!=len(expected) or {item.position for item in result.items}!=expected:
                raise GenerationMismatch('choice_review_incomplete')
            reviews={item.position:item for item in result.items}
            for index,q,signature,_ in batch:
                review=reviews[index+1]
                key=set(q.correct_option_ids or ([q.correct_option_id] if q.options else []))
                valid=(review.answerable and review.explanation_valid and review.scope_preserved and review.confidence>=.8
                    and review.reason_code in ('ok','unchanged_challenge') and set(review.answer_ids)==key and len(review.answer_ids)==len(key))
                solution=independent.get(index+1)
                if solution:valid=valid and solution.answerable and solution.confidence>=.8 and set(solution.answer_ids)==key and len(solution.answer_ids)==len(key)
                if valid:
                    changed=bool(direction and review.requested_change_met and review.change_kind in
                        ('reasoning_steps','scaffolding','representation_transfer') and review.change_basis.strip())
                    self.accepted[signature]=changed
                    q._choice_reviewed=True;q._challenge_change_verified=self.accepted[signature]
                else:
                    invalid.append(index+1)
                    problems.append(dict(position=index+1,reason=review.reason_code if review.reason_code!='ok' else
                        'uncertain' if review.confidence<.8 else 'key_disagreement',detail=review.problem_detail or (solution.problem_detail if solution else '')))
        workflow_logger.event('assessment.choice_review',checked=len(pending),rejected=len(invalid))
        if invalid:raise GenerationMismatch('choice_review_failed',question_indices=invalid,problems=problems)
        reviewed=[(index,q) for index,q in enumerate(questions) if q.options or direction]
        if direction and reviewed and sum(q._challenge_change_verified for _,q in reviewed)<ceil(len(reviewed)*2/3):
            positions=[index+1 for index,q in reviewed if not q._challenge_change_verified]
            # Repaired content must be reviewed again even if the rejected draft
            # was a valid control item.
            raise GenerationMismatch('challenge_change_insufficient',question_indices=positions,
                problems=[dict(position=i,reason='unchanged_challenge') for i in positions])
