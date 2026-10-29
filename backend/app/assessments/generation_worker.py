"""Durable paper generation, independent of the 150-second chat-turn deadline."""
import asyncio
from time import monotonic
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from app.langchain.workflow_budget import model_budget
from .schemas import GenerationRequest, AssessmentIntent


class AssessmentGenerationWorker:
    def __init__(self, service): self.service = service

    async def run_once(self):
        jobs = self.service.generation_jobs
        job = await run_in_threadpool(jobs.claim)
        if not job: return False
        processing = asyncio.create_task(self._process(job))
        async def watch():
            failures = 0
            while not processing.done():
                await asyncio.sleep(.5)
                try:
                    if not await run_in_threadpool(jobs.active, job):
                        processing.cancel()
                        return
                    failures = 0
                except Exception:
                    failures += 1
                    if failures >= 3:
                        processing.cancel()
                        return
        watcher = asyncio.create_task(watch())
        try:
            await processing
        except asyncio.CancelledError:
            if not processing.cancelled(): raise
        finally:
            watcher.cancel()
            if not processing.done(): processing.cancel()
            await asyncio.gather(processing, watcher, return_exceptions=True)
        return True

    async def _process(self, job):
        jobs = self.service.generation_jobs
        intent = AssessmentIntent.model_validate(job['request'])
        request = None
        owner, conversation = job['learner_id'], job['conversation_id']
        repository = self.service.repository
        claim, heartbeat, generation, reservation = None, None, None, None
        stage = 'admission'
        try:
            if self.service.admission:
                context = self.service.admission.async_reserve('model', owner, capacity=16, owner_capacity=2, seconds=1140)
                await context.__aenter__(); reservation = context
            stage = 'selection'
            if conversation: await run_in_threadpool(self.service.chat.recent, owner, conversation)
            if job['progress'].get('resolved_request'):
                request = GenerationRequest.model_validate(job['progress']['resolved_request'])
            else:
                from app.langchain.assessment_selection import resolve_assessment_intent
                with model_budget(deadline=monotonic()+120):
                    request = await asyncio.wait_for(resolve_assessment_intent(self.service.workflows, owner, intent), 120)
                job['progress'] = dict(job['progress'], resolved_request=request.model_dump(mode='json'))
                await run_in_threadpool(jobs.update, job, progress=job['progress'])
            stage = 'replay'
            previous = await run_in_threadpool(self.service.chat.replay, owner, conversation, request) if conversation else await run_in_threadpool(repository.replay, owner, request)
            if previous:
                result = previous if isinstance(previous, dict) else previous.model_dump(mode='json')
                await run_in_threadpool(jobs.update, job, state='completed', result=result, error=None)
                return True
            stage = 'claim'
            claim = await run_in_threadpool(repository.claim_generation, owner, request)
            snapshot = job['progress'].get('mistake_revision')
            revision = dict(questions=snapshot['questions'], instructions=request.instructions, mistake_revision=True) if snapshot else await self.service._revision_source(owner, request, conversation)
            async def checkpoint(value):
                if conversation: await run_in_threadpool(self.service.chat.recent, owner, conversation)
                value = dict(value, resolved_request=request.model_dump(mode='json'))
                if snapshot: value['mistake_revision'] = snapshot
                await run_in_threadpool(jobs.update, job, progress=value)
                job['progress'] = value
                await run_in_threadpool(repository.renew_generation, owner, request.client_request_id, claim)
            async def renew():
                while True:
                    await asyncio.sleep(30)
                    await run_in_threadpool(jobs.update, job)
                    await run_in_threadpool(repository.renew_generation, owner, request.client_request_id, claim)
            heartbeat = asyncio.create_task(renew())
            stage = 'generation'
            with model_budget(deadline=monotonic()+900, max_rounds=256, max_input_tokens=1_000_000, max_total_tokens=2_000_000):
                generation = asyncio.create_task(self.service.workflows.generate(owner, request, revision=revision,
                    checkpoint=checkpoint, resume=job['progress']))
                done, _ = await asyncio.wait([generation, heartbeat], timeout=900, return_when=asyncio.FIRST_COMPLETED)
                if generation not in done:
                    generation.cancel()
                    await asyncio.gather(generation, return_exceptions=True)
                    if heartbeat in done: await heartbeat
                    raise TimeoutError()
                generated, sources = await generation
            if snapshot:
                if len(generated.questions) != len(snapshot['questions']):
                    raise AppError('ASSESSMENT_INVALID_GENERATION', 'Revision question count changed.', 422)
                for question, original in zip(generated.questions, snapshot['questions']):
                    if question.prompt.strip().casefold() == original['prompt'].strip().casefold():
                        raise AppError('ASSESSMENT_INVALID_GENERATION', 'Revision needs fresh question wording.', 422)
                    question.concept_ids = original['concept_ids']
                generated.title = 'Revision assessment'

            stage = 'publication'
            if conversation:
                result = await run_in_threadpool(self.service.chat.save, owner, conversation, request, generated, sources, claim)
            else:
                value = await run_in_threadpool(repository.save, owner, request, generated, sources, claim, snapshot)
                result = value.model_dump(mode='json')
            await run_in_threadpool(jobs.update, job, state='completed', result=result, error=None)
        except Exception as error:
            from app.core.logging import workflow_logger
            code = error.code if isinstance(error, AppError) else type(error).__name__
            workflow_logger.event('assessment.generation_failed', stage=stage,error_code=code,error_type=type(error).__name__)
            message = error.message if isinstance(error, AppError) and error.code in ('ASSESSMENT_SOURCES_REQUIRED','ASSESSMENT_PAPER_MARKS','ASSESSMENT_INVALID_GENERATION','ASSESSMENT_TARGET_CHANGED') else 'Generation was interrupted. Completed sections are kept; retry to continue.'
            try: await run_in_threadpool(jobs.update, job, state='failed', error=message,
                progress=dict(job['progress'],failure=dict(stage=stage,code=code)))
            except AppError: pass  # A newer lease owns publication now.
        finally:
            if generation and not generation.done():
                generation.cancel(); await asyncio.gather(generation, return_exceptions=True)
            if heartbeat:
                heartbeat.cancel(); await asyncio.gather(heartbeat, return_exceptions=True)
            if claim: await run_in_threadpool(repository.release_generation, owner, request.client_request_id, claim)
            if reservation:
                await reservation.__aexit__(None,None,None)
        return True
