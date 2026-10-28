"""Generation survives a disconnected HTTP caller, with durable turn recovery."""
import asyncio
import logging
from app.core.observability.timing import run_in_threadpool
from app.core.exceptions import AppError
from .context import HistoryContextPolicy

logger = logging.getLogger('mentra')


def request_outcome(value):
    turn=value.get('turn') or {}
    state=(turn.get('response_outcome') or {}).get('state')
    return {'completed':'success','failed':'failed','partial':'degraded','in_progress':'deferred',
        'awaiting_input':'deferred','paused':'deferred'}.get(state) or {
        'FAILED':'failed','RUNNING':'deferred','SUCCEEDED':'success'}.get(turn.get('state'),'unknown')


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={
    'send': {'request_outcome': True, 'result': lambda value: dict(domain_status=value.get('turn', {}).get('state', 'unknown')),
             'outcome': request_outcome},
})
class ConversationService:
    def __init__(self, repository, policy=None, summary_llm=None, admission=None):
        self.repository = repository
        self.admission = admission
        self.policy = policy or HistoryContextPolicy()
        self.tasks = set()
        self.turn_tasks = {}
        from .summaries import ConversationSummaries
        self.summaries = ConversationSummaries(repository, summary_llm) if summary_llm else None

    async def send(self, owner, request, generate, *, with_scope=False, wait=True):
        # Disconnects during SQL admission must not leave a committed RUNNING turn
        # without a generation task. The service owns admission through completion.
        origin = workflow_logger.envelope()
        admission = workflow_logger.start_task(self._send(owner, request, generate, with_scope=with_scope, wait=wait,
            log_context=origin), name='chat.admit')
        self.tasks.add(admission)
        admission.add_done_callback(self._admission_done)
        return await asyncio.shield(admission)

    def _admission_done(self, task):
        self.tasks.discard(task)
        if not task.cancelled():
            task.exception()  # Observe failures even when the caller disconnected.

    async def _send(self, owner, request, generate, *, with_scope=False, wait=True, log_context=None):
        if not request.content.strip():
            raise AppError('CHAT_EMPTY_MESSAGE', 'Enter a message.', 422)
        reservation = None
        if self.admission:
            previous = await run_in_threadpool(self.repository.replay_turn, owner, request)
            if previous:
                return previous
            reservation = await run_in_threadpool(self.admission.acquire, 'model', owner,
                capacity=16, owner_capacity=2, seconds=300)
        try:
            job = await run_in_threadpool(self.repository.begin_turn, owner, request, log_context=log_context)
        except BaseException:
            if reservation:
                await run_in_threadpool(self.admission.release, reservation)
            raise
        if reservation and not job['run']:
            await run_in_threadpool(self.admission.release, reservation)
        if job['run']:
            job['_admission'] = reservation
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

    async def stop(self, owner, conversation_id, turn_id, attempt, *, stopped_job=None):
        stopped = await run_in_threadpool(self.repository.stop_turn, owner, conversation_id, turn_id, attempt, stopped_job)
        if stopped:
            task = self.turn_tasks.get((owner, conversation_id, turn_id, attempt))
            if task:
                task.cancel()
        # A newer turn may already exist on another tab. Return the latest
        # canonical page rather than making that new turn appear finished.
        return await run_in_threadpool(self.repository.status, owner, conversation_id)

    async def resume(self, owner, conversation_id, turn_id, body, generate, *, with_scope=True, fingerprint=None):
        # As with Send, the service owns admission through task creation even
        # if the HTTP caller disconnects while the transaction is committing.
        admission = workflow_logger.start_task(self._resume(owner, conversation_id, turn_id, body, generate,
            with_scope=with_scope, fingerprint=fingerprint), name='chat.resume.admit')
        self.tasks.add(admission)
        admission.add_done_callback(self._admission_done)
        return await asyncio.shield(admission)

    async def _resume(self, owner, conversation_id, turn_id, body, generate, *, with_scope=True, fingerprint=None):
        reservation = None
        if self.admission:
            reservation = await run_in_threadpool(self.admission.acquire, 'model', owner,
                capacity=16, owner_capacity=2, seconds=300)
        try:
            job = await run_in_threadpool(self.repository.resume_turn, owner, conversation_id, turn_id,
                body.attempt, body.expected_revision, body.instruction, str(body.client_request_id),
                fingerprint or body.model_dump_json(exclude={'client_request_id'}))
        except BaseException:
            if reservation: await run_in_threadpool(self.admission.release, reservation)
            raise
        if not job['run']:
            if reservation: await run_in_threadpool(self.admission.release, reservation)
            page = await run_in_threadpool(self.repository.status, owner, conversation_id)
            return dict(page, continued_turn_id=turn_id)
        job['_admission'] = reservation
        task = workflow_logger.start_task(self._generate(owner, job, generate, with_scope), name='chat.resume')
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        key = (owner, conversation_id, turn_id, job['attempt'])
        self.turn_tasks[key] = task
        task.add_done_callback(lambda done: self.turn_tasks.pop(key, None))
        page = await run_in_threadpool(self.repository.status, owner, conversation_id)
        return dict(page, continued_turn_id=turn_id)

    async def _watch_active(self, owner, job, generation, history_scope=None):
        # Durable fencing also cancels work when another process handles Stop.
        from .repositories.activity import ActivityRepository
        repository = ActivityRepository(self.repository.sessions)
        failures = 0
        while not generation.done():
            await asyncio.sleep(.5)
            try:
                fence = history_scope.get('_memory_summary_fence') if history_scope and not history_scope.get('_memory_writes_pending') else None
                valid = await run_in_threadpool(repository.ensure_active, owner, job, fence)
                if fence:
                    if history_scope.get('_memory_writes_pending') or history_scope['_memory_summary_fence'] is not fence:
                        failures = 0
                        continue  # Our own write committed while this read was in flight.
                    if not valid:
                        history_scope['_memory_context_changed'] = True
                        await history_scope['activity'].emit('response-stream', 'running', 'Saved memories changed', token_reset=True)
                        generation.cancel()
                        return
                failures = 0
            except AppError as error:
                from app.langchain.tool_execution import LIFECYCLE_CODES
                if error.code in LIFECYCLE_CODES:
                    generation.cancel()
                    return
                failures += 1
            except Exception:
                failures += 1
            if failures:
                workflow_logger.event('chat.watch_unavailable', code='WATCH_DEPENDENCY_UNAVAILABLE', attempt=failures)
                if failures >= 3:
                    # Never continue unmonitored paid work through a sustained outage.
                    generation.cancel()
                    return

    async def _generate(self, owner, job, generate, with_scope=False):
        from time import monotonic
        deadline = monotonic() + 150
        activity_sink = None
        scope = None
        try:
            if self.summaries:
                rows, summary = await self.summaries.load_context(owner, job['conversation_id'], job['user_sequence'])
            else:
                rows = await run_in_threadpool(self.repository.context_rows, owner, job['conversation_id'], job['user_sequence'])
                summary = None
            if summary and summary['through_sequence'] >= job['user_sequence']:
                summary = None  # Never give a retried older turn future context.
            history = [(row['role'], row['content']) for row in rows if row['role'] in ('user', 'assistant')]
            if job.get('resume_instruction'):
                history[-1] = ('user', history[-1][1] + '\n\nRequested changes while paused:\n' + job['resume_instruction'])
                rows = [dict(row, content=history[-1][1]) if row['sequence'] == job['user_sequence'] else row for row in rows]
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
                scope['_response_checkpoint'] = (self.repository.sessions.kw['bind'], owner, job)
                scope['resume_instruction'] = job.get('new_instruction')
                scope['conversation_summary'] = summary
                await scope['activity'].emit('planning', 'running', 'Planning your request')
                invocation = lambda: generate(history, job['selection'], scope)
            else:
                invocation = lambda: generate(history, job['selection'])
            from app.langchain.graphs.response import run_response
            if job.get('background_response'):
                async def invocation(): return job['background_response']
            generation = asyncio.ensure_future(run_response(invocation,
                self.repository.sessions.kw['bind'], owner, job))
            watcher = asyncio.create_task(self._watch_active(owner, job, generation, scope if with_scope else None))
            try:
                response = await asyncio.wait_for(generation, timeout=max(.001, deadline - monotonic()))
            finally:
                generation.cancel()
                watcher.cancel()
                await asyncio.gather(generation, watcher, return_exceptions=True)
            if activity_sink is not None:
                await activity_sink.flush()
            if with_scope and scope.get('_memory_summary_fence'):
                response['_memory_summary_fence'] = scope['_memory_summary_fence']
            if scope:
                from app.langchain.recovery_receipts import capture_recovery
                job['_recovery_state'] = capture_recovery(scope)
            await run_in_threadpool(self.repository.finish, owner, job, response, None)
            from app.core.observability.context import current
            if current.get() and current.get().outcome == 'unknown':
                outcome = (response.get('response_outcome') or {}).get('state')
                current.get().outcome = 'failed' if outcome == 'failed' else 'degraded' if outcome == 'partial' or response.get('retrieval_warning') or response.get('tool_warnings') else 'deferred' if outcome in ('in_progress','awaiting_input') else 'success'
        except asyncio.CancelledError:
            if scope:
                from app.langchain.recovery_receipts import capture_recovery
                job['_recovery_state'] = capture_recovery(scope)
            if scope and scope.get('_memory_context_changed'): job['_discard_checkpoint'] = True
            message = 'Saved memories changed while answering. Retry this message to use current context.' if scope and scope.get('_memory_context_changed') else 'Generation interrupted. Retry this message.'
            await run_in_threadpool(self.repository.finish, owner, job, None, message)
            raise
        except Exception as error:
            job['_failure_code']=error.code if isinstance(error,AppError) else 'CHAT_INTERNAL_ERROR'
            partial = None
            if scope:
                from app.langchain.recovery_receipts import capture_recovery, partial_response
                job['_recovery_state'] = capture_recovery(scope)
                # Lifecycle failures must not publish after stop/deletion or
                # reuse invalidated context. The repository still fences writes.
                if job['_failure_code'] not in ('CHAT_RESUME_CONTEXT_CHANGED','CHAT_ATTEMPT_EXPIRED','CHAT_STALE_ATTEMPT','CHAT_DELETED','CHAT_NOT_FOUND'):
                    partial = partial_response(scope,job['_failure_code'])
            if isinstance(error, AppError) and error.code == 'CHAT_RESUME_CONTEXT_CHANGED': job['_discard_checkpoint'] = True
            from app.core.observability.context import current
            if current.get():
                current.get().outcome = 'failed'
            message = error.message if isinstance(error, AppError) else 'Mentra could not complete this response. Retry this message.'
            if not isinstance(error, AppError):
                logger.error('Persistent chat generation failed (%s)', type(error).__name__)
            await run_in_threadpool(self.repository.finish, owner, job, partial, None if partial else message)
        finally:
            if activity_sink is not None:
                await activity_sink.close()
            if job.get('_admission'):
                try:
                    await run_in_threadpool(self.admission.release, job['_admission'])
                except Exception:
                    workflow_logger.event('admission.cleanup_deferred', code='CLAIM_CLEANUP_UNAVAILABLE')

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
