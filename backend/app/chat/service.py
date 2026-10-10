"""Generation survives a disconnected HTTP caller, with durable turn recovery."""
import asyncio
import logging
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from .context import HistoryContextPolicy

logger = logging.getLogger('mentra')


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={
    'send': {'request_outcome': True, 'result': lambda value: dict(domain_status=value.get('turn', {}).get('state', 'unknown')),
             'outcome': lambda value: {'FAILED':'failed','RUNNING':'deferred','SUCCEEDED':'success'}.get(value.get('turn', {}).get('state'), 'unknown')},
})
class ConversationService:
    def __init__(self, repository, policy=None):
        self.repository = repository
        self.policy = policy or HistoryContextPolicy()
        self.tasks = set()

    async def send(self, owner, request, generate, *, with_scope=False, wait=True):
        if not request.content.strip():
            raise AppError('CHAT_EMPTY_MESSAGE', 'Enter a message.', 422)
        job = await run_in_threadpool(self.repository.begin_turn, owner, request)
        if job['run']:
            task = workflow_logger.start_task(self._generate(owner, job, generate, with_scope), name='chat.generate')
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            if wait:
                await asyncio.shield(task)
        return await run_in_threadpool(self.repository.status, owner, job['conversation_id'], job['turn_id'], True)

    async def _generate(self, owner, job, generate, with_scope=False):
        try:
            rows = await run_in_threadpool(self.repository.context_rows, owner, job['conversation_id'], job['user_sequence'])
            history = [(row['role'], row['content']) for row in rows if row['role'] in ('user', 'assistant')]
            # Context selection runs once, after retrieval, when the complete prompt budget is known.
            if with_scope:
                current = next(row for row in rows if row['sequence'] == job['user_sequence'])
                scope = dict(job, current_user_message_id=current['id'], context_rows=rows,
                    visible_ids=[], visible_user_messages=[], evidence_ids={current['id']},
                    history_references=[], memory_references=[])
                from app.langchain.activity import ActivityPublisher
                from .repositories.activity import ActivityRepository, DurableActivitySink
                scope['activity'] = ActivityPublisher(DurableActivitySink(ActivityRepository(self.repository.sessions), owner, job))
                await scope['activity'].emit('planning', 'running', 'Planning your request')
                invocation = generate(history, job['selection'], scope)
            else:
                invocation = generate(history, job['selection'])
            response = await asyncio.wait_for(invocation, timeout=150)
            await run_in_threadpool(self.repository.finish, owner, job, response, None)
            from app.core.observability.context import current
            if current.get().outcome == 'unknown':
                current.get().outcome = 'degraded' if response.get('retrieval_warning') else 'success'
        except asyncio.CancelledError:
            await run_in_threadpool(self.repository.finish, owner, job, None, 'Generation interrupted. Retry this message.')
            raise
        except Exception as error:
            from app.core.observability.context import current
            if current.get():
                current.get().outcome = 'failed'
            message = error.message if isinstance(error, AppError) else 'Mentra could not complete this response. Retry this message.'
            if not isinstance(error, AppError):
                logger.error('Persistent chat generation failed (%s)', type(error).__name__)
            await run_in_threadpool(self.repository.finish, owner, job, None, message)

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
