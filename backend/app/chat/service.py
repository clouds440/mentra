"""Generation survives a disconnected HTTP caller, with durable turn recovery."""
import asyncio
import logging
from app.core.observability.timing import run_in_threadpool
from app.core.exceptions import AppError
from .context import HistoryContextPolicy

logger = logging.getLogger('mentra')


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={
    'send': {'request_outcome': True, 'result': lambda value: dict(domain_status=value.get('turn', {}).get('state', 'unknown')),
             'outcome': lambda value: {'FAILED':'failed','RUNNING':'deferred','SUCCEEDED':'success'}.get(value.get('turn', {}).get('state'), 'unknown')},
})
class ConversationService:
    def __init__(self, repository, policy=None, summary_llm=None):
        self.repository = repository
        self.policy = policy or HistoryContextPolicy()
        self.tasks = set()
        self.turn_tasks = {}
        from .summaries import ConversationSummaries
        self.summaries = ConversationSummaries(repository, summary_llm) if summary_llm else None

    async def send(self, owner, request, generate, *, with_scope=False, wait=True):
        if not request.content.strip():
            raise AppError('CHAT_EMPTY_MESSAGE', 'Enter a message.', 422)
        job = await run_in_threadpool(self.repository.begin_turn, owner, request)
        if job['run']:
            task = workflow_logger.start_task(self._generate(owner, job, generate, with_scope), name='chat.generate')
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            key = (owner, job['conversation_id'], job['turn_id'], job['attempt'])
            self.turn_tasks[key] = task
            task.add_done_callback(lambda done: self.turn_tasks.pop(key, None) if self.turn_tasks.get(key) is done else None)
            if wait:
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    if not task.cancelled():
                        raise  # Disconnecting the caller must not stop generation.
        return await run_in_threadpool(self.repository.status, owner, job['conversation_id'], job['turn_id'], True)

    async def stop(self, owner, conversation_id, turn_id, attempt):
        stopped = await run_in_threadpool(self.repository.stop_turn, owner, conversation_id, turn_id, attempt)
        if stopped:
            task = self.turn_tasks.get((owner, conversation_id, turn_id, attempt))
            if task:
                task.cancel()
        # A newer turn may already exist on another tab. Return the latest
        # canonical page rather than making that new turn appear finished.
        return await run_in_threadpool(self.repository.status, owner, conversation_id)

    async def _watch_active(self, owner, job, generation):
        # Durable fencing also cancels work when another process handles Stop.
        from .repositories.activity import ActivityRepository
        repository = ActivityRepository(self.repository.sessions)
        while not generation.done():
            await asyncio.sleep(.5)
            try:
                await run_in_threadpool(repository.ensure_active, owner, job)
            except AppError as error:
                if error.code != 'CHAT_ATTEMPT_EXPIRED':
                    raise
                generation.cancel()
                return

    async def _generate(self, owner, job, generate, with_scope=False):
        from time import monotonic
        deadline = monotonic() + 150
        activity_sink = None
        try:
            rows = await run_in_threadpool(self.repository.context_rows, owner, job['conversation_id'], job['user_sequence'])
            summary = await self.summaries.load(owner, job['conversation_id']) if self.summaries else None
            if summary and summary['through_sequence'] >= job['user_sequence']:
                summary = None  # Never give a retried older turn future context.
            history = [(row['role'], row['content']) for row in rows if row['role'] in ('user', 'assistant')]
            # Context selection runs once, after retrieval, when the complete prompt budget is known.
            if with_scope:
                current = next(row for row in rows if row['sequence'] == job['user_sequence'])
                scope = dict(job, interaction_response=current.get('metadata', {}).get('interaction_response'), current_user_message_id=current['id'], context_rows=rows,
                    visible_ids=[], visible_user_messages=[], evidence_ids={current['id']},
                    history_references=[], memory_references=[])
                from app.langchain.activity import ActivityPublisher
                from .repositories.activity import ActivityRepository, DurableActivitySink
                activity_sink = DurableActivitySink(ActivityRepository(self.repository.sessions), owner, job)
                scope['activity'] = ActivityPublisher(activity_sink)
                scope['_generation_deadline'] = deadline
                scope['conversation_summary'] = summary
                await scope['activity'].emit('planning', 'running', 'Planning your request')
                invocation = generate(history, job['selection'], scope)
            else:
                invocation = generate(history, job['selection'])
            generation = asyncio.ensure_future(invocation)
            watcher = asyncio.create_task(self._watch_active(owner, job, generation))
            try:
                response = await asyncio.wait_for(generation, timeout=max(.001, deadline - monotonic()))
            finally:
                generation.cancel()
                watcher.cancel()
                await asyncio.gather(generation, watcher, return_exceptions=True)
            if activity_sink is not None:
                await activity_sink.flush()
            published = await run_in_threadpool(self.repository.finish, owner, job, response, None)
            if self.summaries and published:
                task = workflow_logger.start_task(self.summaries.refresh(owner, job['conversation_id']), name='chat.summarize')
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
            from app.core.observability.context import current
            if current.get().outcome == 'unknown':
                current.get().outcome = 'degraded' if response.get('retrieval_warning') or response.get('tool_warnings') else 'success'
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
        finally:
            if activity_sink is not None:
                await activity_sink.close()

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
