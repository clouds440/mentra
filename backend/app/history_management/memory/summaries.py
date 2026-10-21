"""Bounded incremental generation, independent of interactive request budgets."""
import asyncio
import logging
from starlette.concurrency import run_in_threadpool as dispatch
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.observability.timing import run_in_threadpool
from app.langchain.prompts import PromptSource
from app.langchain.token_policy import check_input
from .summary_schemas import MemorySummary, fits, encoded
from app.summarization.execution import generation

logger = logging.getLogger('mentra')


class MemorySummaries:
    def __init__(self, repository, llm):
        self.repository, self.llm = repository, llm

    async def run_once(self):
        if not settings.memory_summary_enabled:
            return False
        claim = await dispatch(self.repository.claim)
        if not claim:
            return False
        from app.core.logging import workflow_logger
        with workflow_logger.workflow('memory.summarize') as execution:
            try:
                packet = None
                for batch_size in (12, 6, 3, 1):
                    packet = await run_in_threadpool(self.repository.packet, claim, batch_size)
                    if packet is None:
                        break
                    payload = {key:packet[key] for key in ('previous_summary', 'changes', 'removed', 'pinned_supports')}
                    payload['limits'] = dict(max_characters=settings.memory_summary_max_characters,
                        max_context_tokens=settings.memory_summary_max_tokens)
                    try:
                        if len(encoded(packet['changes'])) > 16000:
                            raise ValueError('Delta packet exceeds character limit')
                        check_input(self.llm.messages(PromptSource.MEMORY_SUMMARY, payload), PromptSource.MEMORY_SUMMARY, tools=[MemorySummary])
                        break
                    except (ValueError, AppError):
                        if batch_size == 1:
                            raise
                if packet is None:
                    await run_in_threadpool(self.repository.release, claim)
                    execution.outcome = 'skipped'
                    return True
                allowed = {x['id']: x['revision'] for block in packet['previous_summary'] for x in block['supports']}
                allowed.update({x['id']: x['revision'] for x in packet['changes']})
                for identifier in packet['removed']:
                    allowed.pop(identifier, None)
                if not allowed:
                    blocks = []
                else:
                    async with generation():
                        for repair in range(2):
                            result = await self.llm.ainvoke(PromptSource.MEMORY_SUMMARY, payload, output_schema=MemorySummary)
                            blocks = result.model_dump(mode='json')['blocks']
                            if not blocks or any(not b['text'].strip() for b in blocks):
                                raise ValueError('Empty summary for eligible facts')
                            if any(allowed.get(x['id']) != x['revision'] for b in blocks for x in b['supports']):
                                raise ValueError('Unsupported summary reference')
                            if fits(blocks):
                                break
                            if repair:
                                raise ValueError('Summary exceeds independent limits')
                            payload = dict(previous_summary=blocks, changes=[], removed=[], limits=payload['limits'],
                                compression_repair='Shorten these blocks to fit both limits; preserve their supported meaning.')
                published = await run_in_threadpool(self.repository.publish, claim, packet, blocks)
                workflow_logger.event('memory.summary_completed', published=published, changed_count=len(packet['changes']),
                    source_revision=claim['state']['source_revision'], through_revision=packet['through'], rebuild=packet['rebuild'])
                execution.outcome = 'success' if published else 'skipped'
            except asyncio.CancelledError:
                await run_in_threadpool(self.repository.release, claim)
                raise
            except Exception as error:
                await run_in_threadpool(self.repository.release, claim, error)
                execution.outcome = 'failed'
                logger.warning('Memory summary deferred (%s)', type(error).__name__)
        return True
