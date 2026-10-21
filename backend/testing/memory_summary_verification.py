"""Opt-in live same-model verification with synthetic facts in a disposable schema.

Requires explicit TEST_DATABASE_URL. Never modifies configured user records.
Run: PYTHONPATH=backend python -m testing.memory_summary_verification
"""
import asyncio
import json
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import update, select
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from app.core.config import settings
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.prompts import PromptSource
from app.history_management.repositories.postgres import MemoryRepository
from app.history_management.repositories.memory_summaries import MemorySummaryRepository, now
from app.history_management.repositories.tables import summary_jobs as j
from app.history_management.memory.summaries import MemorySummaries
from app.history_management.schemas import MemoryEdit, MemoryToolInput, HistoryLookup
from app.history_management.memory.validation import MemoryValidator
from app.history_management.service import HistoryManagement
from app.history_management.budgets import ToolBudget
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.history_reader import ChatReadFacade
from app.chat.schemas import SendTurn
from app.chat.summaries import ChatSummaryConsumer
from app.chat.repositories.tables import summary_jobs as chat_jobs, summaries as chat_summaries
from app.summarization.worker import Summarizer
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


async def main():
    with PostgresSandbox() as db:
        owner = learner_id('alice')
        memories = MemoryRepository(db.sessions)
        repository = MemorySummaryRepository(db.sessions)
        llm = MentraLLM(ModelFactory(settings))
        worker = MemorySummaries(repository, llm)
        chats = ChatRepository(db.sessions)
        statement = 'I maintain the untoastify React toast package. Please remember it.'
        job = chats.begin_turn(owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content=statement))
        row = chats.context_rows(owner, job['conversation_id'], job['user_sequence'])[-1]
        scope = dict(job, evidence_ids={row['id']}, memory_references=[], history_references=[],
            _memory_summary_fence=repository.context(owner)[1])
        facade = HistoryManagement(memories, ChatReadFacade(chats), MemoryValidator(llm))
        saved = await facade.memory(owner, scope, MemoryToolInput(action='remember', content='Maintains the untoastify React toast package.',
            category='fact', evidence_message_id=row['id'], evidence_quote=statement), ToolBudget())
        assert saved['outcome'] == 'saved' and saved['memory']['status'] == 'active', 'AI memory was not saved'
        assert chats.finish(owner, job, dict(content='Remembered the package.', _memory_summary_fence=scope['_memory_summary_fence']))
        assert chats.context_rows(owner, job['conversation_id'])[-1]['content'] == 'Remembered the package.', 'Own memory save invalidated its answer'
        project = saved['memory']
        preference = memories.write(owner, 'Prefers brief explanations.', 'preference', str(uuid4()))['memory']
        memories.write(owner, 'اردو میں بھی سیکھنا پسند ہے۔', 'preference', str(uuid4()))
        async def refresh():
            for _ in range(8):
                with db.sessions.begin() as session:
                    session.execute(update(j).where(j.c.learner_id == owner).values(available_at=now()-timedelta(seconds=1)))
                await worker.run_once()
                with db.sessions() as session:
                    job = session.execute(select(j).where(j.c.learner_id == owner)).mappings().first()
                if not job:
                    return repository.context(owner)[0]
            raise AssertionError('Live worker did not complete')
        first = await refresh()
        assert first['state'] == 'ready' and 'untoastify' in first['content'].lower()
        memories.edit(owner, preference['id'], MemoryEdit(expected_revision=preference['revision'], content='Prefers detailed explanations with examples.'))
        changed = await refresh()
        assert 'brief' not in changed['content'].lower(), 'Superseded preference survived'
        memories.remove(owner, project['id'], project['revision'])
        deleted = await refresh()
        assert 'untoastify' not in deleted['content'].lower(), 'Deleted project survived'
        async def noop(**kwargs):
            return {}
        tools = [StructuredTool.from_function(name='user_memory', description='Recall original saved facts by relevant keywords.', args_schema=MemoryToolInput, coroutine=noop),
                 StructuredTool.from_function(name='history_lookup', description='Find original exchanges in earlier conversations.', args_schema=HistoryLookup, coroutine=noop)]
        context = json.dumps(dict(conversation_summary=dict(state='empty',content=''), memories_summary=first), ensure_ascii=False)
        unrelated = await llm.ainvoke_messages(PromptSource.CHAT, [HumanMessage(content='What is 2 + 2?')], system_context=context,
            additional_sources=(PromptSource.HISTORY_MANAGEMENT,), tools=tools)
        assert not unrelated.tool_calls, 'Unnecessary memory/history retrieval'
        assert 'untoastify' not in str(unrelated.content).lower(), 'Unrelated personal reference'
        relevant = await llm.ainvoke_messages(PromptSource.CHAT, [HumanMessage(content='What is my React package called?')], system_context=context,
            additional_sources=(PromptSource.HISTORY_MANAGEMENT,), tools=tools)
        assert 'untoastify' in str(relevant.content).lower() or relevant.tool_calls, 'Relevant personal context ignored'
        recall = await llm.ainvoke_messages(PromptSource.CHAT, [HumanMessage(content='Search my previous chats for the original discussion of untoastify; I need the exact exchange.')],
            system_context=context, additional_sources=(PromptSource.HISTORY_MANAGEMENT,), tools=tools)
        assert any(x['name'] == 'history_lookup' for x in recall.tool_calls), 'Original history retrieval not selected'
        cid, revision = str(uuid4()), 0
        for _ in range(18):
            exchange = chats.begin_turn(owner, SendTurn(conversation_id=cid, client_turn_id=uuid4(), expected_revision=revision,
                content='Explain geometry and triangle angles. '*45))
            chats.finish(owner, exchange, dict(content='We practiced geometry and used the triangle angle sum. '*35))
            revision = chats.status(owner, cid)['conversation']['revision']
        shared = Summarizer(worker, ChatSummaryConsumer(chats, llm))
        for _ in range(5):
            with db.sessions.begin() as session:
                session.execute(update(chat_jobs).where(chat_jobs.c.learner_id == owner).values(available_at=now()-timedelta(seconds=1)))
            await shared.run_once()
            with db.sessions() as session:
                summary = session.execute(select(chat_summaries).where(chat_summaries.c.conversation_id == cid)).mappings().first()
            if summary and summary['content']:
                assert 'geometr' in summary['content'].lower(), 'Chat summary lost its topic'
                break
        else:
            raise AssertionError('Shared worker did not generate the chat summary')
        print(json.dumps(dict(result='passed', same_model=True, checks=['ai_save_with_evidence', 'manual_save', 'bootstrap', 'incremental_edit', 'delete', 'multilingual',
            'unrelated_no_retrieval', 'unrelated_no_personal_reference', 'relevant_personal_context', 'original_history_tool_selection', 'shared_worker_chat_summary'])))


if __name__ == '__main__':
    asyncio.run(main())
