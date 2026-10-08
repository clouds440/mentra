"""Generation survives a disconnected HTTP caller, with durable turn recovery."""
import asyncio
import logging
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from .context import HistoryContextPolicy

logger = logging.getLogger('mentra')


class ConversationService:
    def __init__(self, repository, policy=None):
        self.repository = repository
        self.policy = policy or HistoryContextPolicy()
        self.tasks = set()

    async def send(self, owner, request, generate):
        if not request.content.strip():
            raise AppError('CHAT_EMPTY_MESSAGE', 'Enter a message.', 422)
        job = await run_in_threadpool(self.repository.begin_turn, owner, request)
        if job['run']:
            task = asyncio.create_task(self._generate(owner, job, generate))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            await asyncio.shield(task)
        return await run_in_threadpool(self.repository.status, owner, job['conversation_id'], job['turn_id'], True)

    async def _generate(self, owner, job, generate):
        try:
            rows = await run_in_threadpool(self.repository.context_rows, owner, job['conversation_id'], job['user_sequence'])
            history = [(row['role'], row['content']) for row in rows if row['role'] in ('user', 'assistant')]
            # Context selection runs once, after retrieval, when the complete prompt budget is known.
            response = await asyncio.wait_for(generate(history, job['selection']), timeout=150)
            await run_in_threadpool(self.repository.finish, owner, job, response, None)
        except asyncio.CancelledError:
            await run_in_threadpool(self.repository.finish, owner, job, None, 'Generation interrupted. Retry this message.')
            raise
        except Exception as error:
            message = error.message if isinstance(error, AppError) else 'Mentra could not complete this response. Retry this message.'
            if not isinstance(error, AppError):
                logger.exception('Persistent chat generation failed')
            await run_in_threadpool(self.repository.finish, owner, job, None, message)

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
