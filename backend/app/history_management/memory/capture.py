"""Quiet semantic capture; no extra model call or acknowledgement in a chat reply."""
import asyncio
from time import monotonic
from datetime import timedelta
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import workflow_logger
from app.core.observability.timing import run_in_threadpool
from app.langchain.prompts import PromptSource
from app.summarization.execution import generation, SummaryDeferred
from .capture_schemas import MemoryCapture
from .validation import SECRET
from ..repositories.postgres import MemoryRepository, now
from ..repositories.memory_capture import MemoryCaptureRepository


class AutomaticMemories:
    def __init__(self, sessions, llm, semantic=None):
        self.jobs = MemoryCaptureRepository(sessions)
        self.memories = MemoryRepository(sessions, settings.memory_active_limit, settings.memory_pending_limit)
        self.llm = llm
        from .semantic import MemorySemanticLookup
        self.semantic=semantic or MemorySemanticLookup(sessions)

    def close(self):self.semantic.close()

    async def run_once(self):
        if not settings.memory_capture_enabled: return False
        claim = await run_in_threadpool(self.jobs.claim)
        if not claim: return False
        with workflow_logger.workflow('memory.capture') as execution:
            try:
                from ..repositories.memory_summaries import MemorySummaryRepository
                _, fence = await run_in_threadpool(MemorySummaryRepository(self.jobs.sessions).context, claim['learner_id'])
                packet = await run_in_threadpool(self.jobs.packet, claim)
                if packet is None:
                    await run_in_threadpool(self.jobs.finish, claim)
                    execution.outcome = 'skipped'; return True
                message = packet['source']; text = packet['text']
                if not text.strip() or SECRET.search(message['content']) or text.strip().casefold() in {'ok', 'okay', 'thanks', 'thank you', 'yes', 'no', '👍'}:
                    await run_in_threadpool(self.jobs.finish, claim, packet=packet)
                    execution.outcome = 'skipped'; return True
                related = await run_in_threadpool(self.memories.related, claim['learner_id'], text[:4000], [])
                semantic=[]
                if packet['active_count']>12:
                    semantic,ready=await run_in_threadpool(self.semantic.related,claim['learner_id'],text)
                    if not ready:raise SummaryDeferred(now()+timedelta(seconds=15 if getattr(self.semantic,'retry_after',0)>monotonic() else 1))
                existing = list({str(row['id']): row for row in [*semantic,*related, *packet['existing']]}.values())[:20]
                payload = dict(user_message=text, contextual_prefix=packet['prefix'], source_date=message['created_at'].isoformat(),
                    current_profile=packet['profile'], existing=[{key:(str(item[key]) if key=='id' else
                        item[key].isoformat() if hasattr(item[key],'isoformat') else item[key])
                        for key in ('id','content','revision','status','category','origin','pinned','source_at','expires_at') if key in item} for item in existing])
                from app.langchain.token_policy import check_input
                while True:
                    try:
                        check_input(self.llm.messages(PromptSource.MEMORY_CAPTURE, payload), PromptSource.MEMORY_CAPTURE, tools=[MemoryCapture])
                        break
                    except AppError as error:
                        if error.code != 'AI_CONTEXT_LIMIT': raise
                        if len(existing) > 4:
                            existing = existing[:max(4, len(existing)//2)]
                            payload['existing'] = payload['existing'][:len(existing)]
                        elif len(text) > 256:
                            text = text[:len(text)//2]; payload['user_message'] = text
                        else: raise
                packet.update(next_offset=claim['content_offset']+len(text),
                    complete=claim['content_offset']+len(text) >= len(message['content']))
                # One combined extraction/admission call; no per-candidate calls.
                async with generation():
                    result = await self.llm.ainvoke(PromptSource.MEMORY_CAPTURE, payload, output_schema=MemoryCapture)
                from ..repositories.memory_reconciliation import MemoryReconciler
                # Validate IDs against exactly the packet that reached the model,
                # not candidates discarded while admitting its input budget.
                admitted={item['id'] for item in payload['existing']}
                existing=[item for item in existing if str(item['id']) in admitted]
                outcomes=await run_in_threadpool(MemoryReconciler(self.memories).apply,claim['learner_id'],claim,
                    dict(packet,text=text),result.items,existing,fence)
                workflow_logger.event('memory.capture_completed', candidate_count=len(result.items), outcomes=outcomes,
                    source_complete=packet['complete'])
                execution.outcome = 'success'
            except SummaryDeferred as error:
                await run_in_threadpool(self.jobs.finish, claim, retry_at=error.until)
                execution.outcome = 'deferred'
            except asyncio.CancelledError:
                await run_in_threadpool(self.jobs.finish, claim, retry_at=now()+timedelta(seconds=2))
                raise
            except Exception as error:
                cancelled = isinstance(error, AppError) and error.code in ('MEMORY_CAPTURE_CANCELLED', 'MEMORY_NOT_FOUND', 'CHAT_NOT_FOUND')
                await run_in_threadpool(self.jobs.finish, claim, error=None if cancelled else error)
                workflow_logger.event('memory.capture_failed', error_code=type(error).__name__, cancelled=cancelled)
                execution.outcome = 'skipped' if cancelled else 'failed'
        return True
