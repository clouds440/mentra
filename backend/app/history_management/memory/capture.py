"""Quiet semantic capture; no extra model call or acknowledgement in a chat reply."""
import asyncio
from datetime import timedelta
from hashlib import sha256
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import workflow_logger
from app.core.observability.timing import run_in_threadpool
from app.langchain.prompts import PromptSource
from app.summarization.execution import generation, SummaryDeferred
from .capture_schemas import MemoryCapture
from .validation import MemoryValidator, SECRET
from ..repositories.postgres import MemoryRepository, fingerprint, now
from ..repositories.memory_capture import MemoryCaptureRepository


class AutomaticMemories:
    def __init__(self, sessions, llm):
        self.jobs = MemoryCaptureRepository(sessions)
        self.memories = MemoryRepository(sessions, settings.memory_active_limit, settings.memory_pending_limit)
        self.llm = llm

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
                existing = list({str(row['id']): row for row in [*related, *packet['existing']]}.values())[:17]
                payload = dict(user_message=text, contextual_prefix=packet['prefix'], source_date=message['created_at'].isoformat(),
                    current_profile=packet['profile'], existing=[dict(id=str(item['id']), content=item['content'], revision=item['revision'], status=item['status']) for item in existing])
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
                outcomes = {}
                scope = dict(_capture_claim=claim, _memory_summary_fence=fence, turn_id=claim['turn_id'], conversation_id=claim['conversation_id'])
                for item in result.items:
                    if item.evidence_quote not in text: continue
                    decision = MemoryValidator.admit(item.content, item.evidence_quote, message['content'], existing, item.admission)
                    if decision['outcome'] not in ('active', 'conflict'): continue
                    if item.equivalent_memory_id and any(str(row['id']) == str(item.equivalent_memory_id) and row['status'] == 'active' for row in existing):
                        continue
                    days = {'fact': settings.memory_fact_days, 'goal': settings.memory_goal_days, 'preference': settings.memory_preference_days}[item.category]
                    expiry = message['created_at'] + timedelta(days=days)
                    if decision.get('valid_until'): expiry = min(expiry, decision['valid_until'])
                    if expiry <= now(): continue
                    operation = sha256(f"automatic:{claim['message_id']}:{item.category}:{fingerprint(item.content)}".encode()).hexdigest()
                    receipt = await run_in_threadpool(self.memories.write, claim['learner_id'], item.content, item.category, operation,
                        origin='ai', status=decision['outcome'], conflict_ids=decision.get('conflict_ids', []), expires_at=expiry, scope=scope,
                        evidence=dict(conversation_id=claim['conversation_id'], message_id=claim['message_id'], quote=item.evidence_quote,
                            source_date=message['created_at'], source_deleted=False, explicit_consent=decision['explicit_consent']))
                    outcomes[receipt['outcome']] = outcomes.get(receipt['outcome'], 0)+1
                await run_in_threadpool(self.jobs.finish, claim, packet=packet)
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
