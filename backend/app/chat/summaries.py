"""Incremental background compaction; no paid call on short or unchanged chats."""
import asyncio
import json
import logging
from langchain_core.messages import HumanMessage
from app.core.config import settings
from app.core.observability.timing import run_in_threadpool
from app.langchain.token_policy import count_messages
from .repositories.summaries import SummaryRepository

logger = logging.getLogger('mentra')


def displaced(rows, through):
    """Keep a complete recent suffix. Summarize only new, completed exchanges."""
    rows = [r for r in rows if r['role'] in ('user', 'assistant')]
    split = len(rows)
    cost = 0
    while split > 0:
        start = split-1
        while start > 0 and rows[start]['role'] != 'user':
            start -= 1
        packet = rows[start:split]
        size = count_messages([HumanMessage(content=r['content']) for r in packet])
        if cost+size > settings.chat_history_token_budget and cost:
            break
        cost += size
        split = start
    return [r for r in rows[:split] if r['sequence'] > through]


def batch(rows):
    """Bound a whole batch; an oversized exchange becomes referenced excerpts."""
    selected = []
    cost = count_messages([HumanMessage(content='[]')])
    protocol = count_messages([HumanMessage(content='')])
    for row in rows:
        text = row['content']
        if count_messages([HumanMessage(content=text)]) > 2000:
            text = text[:800]+'\n[Large original message: retrieve by ID for exact content]\n'+text[-800:]
        item = dict(id=row['id'], sequence=row['sequence'], role=row['role'], content=text)
        size = count_messages([HumanMessage(content=json.dumps(item, ensure_ascii=False))]) - protocol + 2
        if cost + size > 5000:
            break
        selected.append(item)
        cost += size
    # Never publish coverage ending between a user question and its answer.
    while selected and selected[-1]['role'] != 'assistant':
        selected.pop()
    # Verify the assembled payload once; avoid repeatedly tokenizing a growing
    # history packet on the API event loop (quadratic work in short-message chats).
    while selected and count_messages([HumanMessage(content=json.dumps(selected, ensure_ascii=False))]) > 5000:
        selected.pop()
        while selected and selected[-1]['role'] != 'assistant':
            selected.pop()
    return selected


def enough_history(rows):
    cost = 0
    for row in rows:
        cost += count_messages([HumanMessage(content=row['content'])])
        if cost >= 2000:
            return True
    return False


class ConversationSummaries:
    def __init__(self, chats, llm):
        self.chats, self.llm = chats, llm
        self.repository = SummaryRepository(chats)

    async def load(self, owner, chat):
        if not settings.chat_summary_enabled:
            return None
        try:
            row = await run_in_threadpool(self.repository.load, owner, chat)
        except Exception as error:
            from app.core.exceptions import AppError
            if isinstance(error, AppError) and error.status_code in (403, 404):
                raise
            logger.warning('Chat summary read deferred (%s)', type(error).__name__)
            return None
        return dict(content=row['content'], through_sequence=row['through_sequence'], revision=row['revision']) if row and row['content'] else None

    async def candidates(self, owner, chat, through):
        # The retained suffix must come from the actual END of the conversation,
        # not the end of an oldest-first bounded backlog page.
        recent = await run_in_threadpool(self.chats.context_rows, owner, chat)
        old = displaced(recent, 0)
        before = old[-1]['sequence']+1 if old else recent[0]['sequence'] if recent else 0
        return await run_in_threadpool(self.chats.summary_rows, owner, chat, through, before)

    async def refresh(self, owner, chat):
        if not settings.chat_summary_enabled:
            return
        claim = None
        failed = False
        try:
            existing = await run_in_threadpool(self.repository.load, owner, chat)
            from .repositories.postgres import now
            if existing and existing['lease_until'] and existing['lease_until'] > now():
                return  # A pending job or cooldown needs no backlog scan/tokenization.
            candidates = await self.candidates(owner, chat, (existing or {}).get('through_sequence', 0))
            if not enough_history(candidates):
                return
            claim = await run_in_threadpool(self.repository.claim, owner, chat)
            if not claim:
                return
            new_rows = await self.candidates(owner, chat, claim['through_sequence'])
            if not enough_history(new_rows):
                return  # Another process may have finished since our initial read.
            candidates = batch(new_rows)
            if not candidates:
                return
            from app.langchain.prompts import PromptSource
            from app.langchain.workflow_budget import current_budget
            token = current_budget.set(None)  # Independent of the finished answer's deadline/budget.
            try:
                async with asyncio.timeout(45):
                    response = await self.llm.ainvoke(PromptSource.CHAT_SUMMARY,
                        dict(previous_summary=claim['content'], messages=candidates))
            finally:
                current_budget.reset(token)
            content = response.content
            if (getattr(response, 'response_metadata', {}).get('finish_reason') == 'length'
                    or not isinstance(content, str) or not content.strip()
                    or count_messages([HumanMessage(content=content)]) > 650):
                raise ValueError('Invalid summary')
            await run_in_threadpool(self.repository.publish, owner, chat, claim, content.strip(), candidates[-1]['sequence'])
        except asyncio.CancelledError:
            failed = True
            raise
        except Exception as error:
            failed = True
            logger.warning('Chat summary deferred (%s)', type(error).__name__)
        finally:
            if claim:
                try:
                    await run_in_threadpool(self.repository.release, owner, chat, claim['lease_token'], failed=failed)
                except Exception as error:
                    logger.warning('Chat summary lease release deferred (%s)', type(error).__name__)
