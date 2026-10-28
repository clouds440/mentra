"""One model instance and bounded worker pool for both durable summary queues."""
import argparse
import asyncio
import signal


class Summarizer:
    def __init__(self, memory, chat, capture=None):
        self.consumers = (memory, chat, capture) if capture is not None else (memory, chat)
        self.next_kind = 0

    async def run_once(self):
        # Alternate the first queue checked, even with one execution slot.
        first = self.next_kind
        self.next_kind = (first+1) % len(self.consumers)
        for index in ((first+offset) % len(self.consumers) for offset in range(len(self.consumers))):
            if await self.consumers[index].run_once():
                return True
        return False


async def run():
    from uuid import UUID
    from app.core.config import settings
    settings.database_role = 'worker'
    from app.core.logging import configure_logging, logger
    from app.db.database import init_db, get_session_factory
    from app.langchain.model_factory import ModelFactory
    from app.langchain.llm import MentraLLM
    from starlette.concurrency import run_in_threadpool
    from app.history_management.repositories.memory_summaries import MemorySummaryRepository
    from app.history_management.memory.summaries import MemorySummaries
    from app.chat.repositories.postgres import ChatRepository
    from app.chat.summaries import ChatSummaryConsumer
    configure_logging('summarizer')
    init_db()
    sessions = get_session_factory()
    memories = MemorySummaryRepository(sessions)
    llm = MentraLLM(ModelFactory(settings))
    chats = ChatSummaryConsumer(ChatRepository(sessions), llm)
    from app.history_management.memory.capture import AutomaticMemories
    capture = AutomaticMemories(sessions, llm)
    parser = argparse.ArgumentParser()
    parser.add_argument('--retry-owner', type=UUID, help='Owner of the memories or chat to retry.')
    parser.add_argument('--chat', type=UUID, help='With --retry-owner, retry this chat instead of memories.')
    parser.add_argument('--diagnostics', action='store_true')
    parser.add_argument('--backfill-memories', type=UUID, help='Queue recent original messages for one opted-in owner; never seed example facts.')
    args = parser.parse_args()
    if args.diagnostics:
        print(dict(memories=memories.diagnostics(), chats=chats.jobs.diagnostics(), capture=capture.jobs.diagnostics()))
        return
    if args.backfill_memories:
        print(dict(queued=capture.jobs.backfill(str(args.backfill_memories))))
        return
    if args.chat and not args.retry_owner:
        parser.error('--chat requires --retry-owner')
    if args.retry_owner:
        if args.chat:
            chats.jobs.retry(str(args.retry_owner), str(args.chat))
        else:
            memories.retry(str(args.retry_owner))
        return
    service = Summarizer(MemorySummaries(memories, llm), chats, capture)
    stopping = asyncio.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stopping.set())
    async def wait(seconds):
        try:
            await asyncio.wait_for(stopping.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def consume():
        while not stopping.is_set():
            try:
                processed = await service.run_once()
            except Exception as error:
                logger.warning('Summary job deferred (%s)', type(error).__name__)
                processed = False
            if not processed:
                await wait(1)

    async def maintain():
        while not stopping.is_set():
            try:
                if settings.memory_summary_enabled:
                    await run_in_threadpool(memories.sweep)
            except Exception as error:
                logger.warning('Summary expiry sweep deferred (%s)', type(error).__name__)
            await wait(5)

    # Independent slots keep working when another summary/provider call is slow.
    await asyncio.gather(maintain(), *(consume() for _ in range(settings.summarizer_concurrency)))


if __name__ == '__main__':
    asyncio.run(run())
