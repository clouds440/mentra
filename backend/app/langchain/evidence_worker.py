"""Durable typed learning capture after response publication; no mastery writes."""
import asyncio
from collections import Counter
from time import monotonic
from app.core.logging import workflow_logger
from app.core.observability.timing import run_in_threadpool
from app.learner.schemas import LearnerContextPacket
from app.learner.signal_schemas import LearningSignalExtraction
from app.learner.signals import admit_signals
from .prompts import PromptSource
from .signal_payloads import capture_windows


@workflow_logger.connect_module(ignore=('run_once',))
class ChatEvidenceWorker:
    def __init__(self,repository,llm,learner,admission=None):
        self.repository,self.llm,self.learner,self.admission=repository,llm,learner,admission

    async def run_once(self):
        job=await run_in_threadpool(self.repository.claim)
        if not job: return False
        with workflow_logger.workflow('chat.learning_signals',log_context=job.get('log_context')) as execution:
            workflow_logger.event('job.claimed',job_id=str(job['turn_id']),attempt=job['capture_attempt'],source_count=len(job['sources']))
            try:
                if job['formal_assessment']:
                    await run_in_threadpool(self.repository.complete_signals,job,[],'formal_assessment_managed',{})
                    return True
                if not any(source['text'].strip() for source in job['sources']):
                    await run_in_threadpool(self.repository.complete_signals,job,[],'empty_source',{})
                    return True
                async with asyncio.timeout(55):
                    from .assessment_context import optional_read
                    context_ids=job['turn']['selection'].get('context_ids') or None
                    query=job['user']['content'] or next(source['text'] for source in job['sources'] if source['text'].strip())
                    prepared=await run_in_threadpool(optional_read,'chat_signal_context',lambda:
                        self.learner.get_assessment_selection_context(job['owner'],context_ids,query[:4000]))
                    packet=prepared[1] if prepared else LearnerContextPacket()
                    known={item.concept_id:item for item in packet.concepts}
                    progress=job['progress'] if job['progress'].get('source_hash')==job['source_hash'] else {}
                    windows=dict(progress.get('windows') or {})
                    skipped=set(progress.get('quoted_sources') or [])
                    previous=job['previous_receipt']
                    unchanged={source['id'] for source in job['sources']
                        if previous.get('source_revisions',{}).get(source['id'])==source['revision']
                        and previous.get('source_coverage',{}).get(source['id']) in ('complete','quoted_material_not_indexed')}
                    from app.db.admission import background_capacity
                    from .workflow_budget import model_budget
                    async with background_capacity(self.admission,job['owner'],seconds=70):
                        with model_budget(deadline=monotonic()+50,max_rounds=64,max_input_tokens=500_000,max_total_tokens=700_000):
                            for key,payload in capture_windows(self.llm,job,packet):
                                source=payload['source']
                                if source['id'] in skipped or source['id'] in unchanged: continue
                                if key not in windows:
                                    result=await self.llm.ainvoke(PromptSource.CHAT_EVIDENCE,payload,
                                        output_schema=LearningSignalExtraction)
                                    adjusted=[]
                                    for item in result.signals:
                                        if item.source_id!=source['id']:
                                            adjusted.append(item.model_copy(update={'source_id':'__unavailable_window_source__'}))
                                            continue
                                        # A unique exact quote establishes coordinates even
                                        # when model arithmetic supplied an incorrect offset.
                                        # Never repair wording or guess among repeated quotes.
                                        if item.source_id==source['id']:
                                            offset=source['text'].find(item.quote)
                                            if offset>=0 and source['text'].find(item.quote,offset+1)<0:
                                                item=item.model_copy(update=dict(start=source['offset']+offset,
                                                    end=source['offset']+offset+len(item.quote)))
                                        if item.start is not None and (item.start<source['offset'] or
                                                (item.end if item.end is not None else item.start+len(item.quote))>source['offset']+len(source['text'])):
                                            item=item.model_copy(update={'source_id':'__unavailable_window_source__'})
                                        adjusted.append(item)
                                    result=result.model_copy(update={'signals':adjusted})
                                    windows[key]=result.model_dump(mode='json')
                                    if source['kind']=='attachment' and result.disposition=='quoted_material':
                                        skipped.add(source['id'])
                                    await run_in_threadpool(self.repository.checkpoint,job,
                                        dict(source_hash=job['source_hash'],windows=windows,quoted_sources=sorted(skipped)))
                    accepted={};rejected=Counter();dispositions=[]
                    for value in windows.values():
                        result=LearningSignalExtraction.model_validate(value)
                        signals,invalid=admit_signals(result,job['sources'],job['question'],known,packet.context_ids)
                        accepted.update({signal['fingerprint']:signal for signal in signals})
                        rejected.update(invalid);dispositions.append(result.disposition)
                    disposition='captured' if accepted else 'unsupported_observation' if rejected or 'learning_signals' in dispositions else dispositions[-1] if dispositions else 'no_supported_signal'
                    if accepted and all(item['status']=='pending' for item in accepted.values()):
                        disposition='captured_pending_review'
                    if job['unavailable_attachments']:
                        disposition='captured_partial_sources' if accepted else 'attachment_text_unavailable'
                    job['source_coverage']={source['id']:previous.get('source_coverage',{}).get(source['id'],source['coverage'])
                        if source['id'] in unchanged else 'quoted_material_not_indexed' if source['id'] in skipped else source['coverage'] for source in job['sources']}
                    await run_in_threadpool(self.repository.complete_signals,job,list(accepted.values()),disposition,dict(rejected))
                execution.outcome='success'
            except Exception as error:
                execution.outcome='failed'
                from app.core.exceptions import AppError
                deferred=isinstance(error,AppError) and error.code=='WORK_CAPACITY'
                reason='capacity_deferred' if deferred else 'capture_deadline' if isinstance(error,TimeoutError) else 'source_expired' if isinstance(error,AppError) and error.code=='EVIDENCE_SOURCE_EXPIRED' else 'classifier_failure'
                await run_in_threadpool(self.repository.fail,job,deferred=deferred,reason=reason)
                workflow_logger.event('learner.signal_capture_failed',reason=reason,error_type=type(error).__name__)
        return True
