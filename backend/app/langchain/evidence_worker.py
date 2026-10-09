import asyncio
import logging
from .evidence_schemas import DemonstrationExtraction
from .prompts import PromptSource
from app.learner.schemas import LearnerContextRequest,EvidenceSubmissionRequest

class ChatEvidenceWorker:
    def __init__(self,repository,llm,learner):self.repository,self.llm,self.learner=repository,llm,learner
    async def run_once(self):
        from starlette.concurrency import run_in_threadpool
        job=await run_in_threadpool(self.repository.claim)
        if not job:return False
        try:
            packet=await run_in_threadpool(self.learner.get_relevant_context,LearnerContextRequest(learner_id=job['owner'],query=(job['question']+'\n'+job['user']['content'])[:4000],max_concepts=8,include_related=False))
            allowed={concept.concept_id for concept in packet.concepts}
            result=await asyncio.wait_for(self.llm.ainvoke(PromptSource.CHAT_EVIDENCE,dict(question=job['question'][:8000],answer=job['user']['content'],concepts=packet.model_dump(mode='json')),output_schema=DemonstrationExtraction),60) if allowed else DemonstrationExtraction(assessable=False)
            requests=[]
            if result.assessable:
                for item in result.observations:
                    if item.concept_id not in allowed or item.quote not in job['user']['content'] or item.confidence<.85:continue
                    requests.append(EvidenceSubmissionRequest(learner_id=job['owner'],concept_id=item.concept_id,context_id=packet.context_ids[0] if len(packet.context_ids)==1 else None,
                        source_type='CHAT',source_id=f"chat:{job['turn_id']}:{job['attempt']}:{item.concept_id}",item_id=job['user']['id'],session_id=job['turn']['conversation_id'],
                        result='CORRECT' if item.score==item.max_score else 'INCORRECT' if item.score==0 else 'PARTIAL',score=item.score,max_score=item.max_score,difficulty=item.difficulty,
                        independence=item.independence,hint_count=item.hint_count,attempt_number=1,evidence_confidence=item.confidence,occurred_at=job['user']['created_at'],
                        metadata=dict(message_id=job['user']['id'],turn_id=job['turn_id'],prompt_version='chat-demonstration-v1')))
            def apply(tx):return [result.model_dump(mode='json') for result in self.learner.submit_evidence_batch_in_transaction(requests,tx)] if requests else None
            await run_in_threadpool(self.repository.complete,job,apply)
        except Exception as error:
            await run_in_threadpool(self.repository.fail,job)
            logging.getLogger('mentra').warning('Chat evidence job failed (%s)',type(error).__name__)
        return True
