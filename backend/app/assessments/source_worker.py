"""Long answer-sheet extraction never depends on a browser connection."""
import asyncio
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from app.core.logging import workflow_logger
from .repositories.source_jobs import SourceJobs, LEASE_SECONDS


class SourceWorker:
    def __init__(self, service):
        self.service, self.jobs = service, SourceJobs(service.repository)

    async def run_once(self):
        job = await run_in_threadpool(self.jobs.claim)
        if not job: return False
        with workflow_logger.workflow('assessment.source_extraction'):
            try:
                async with self.service.admission.async_reserve('parse',job['learner_id'],capacity=4,owner_capacity=1,seconds=LEASE_SECONDS):
                    async def process():
                        return await self.service.upload_paper_with_vision(job['learner_id'],job['attempt_id'],
                            job['expected_revision'],job['file_id'], from_chat=job['from_chat'],source_job=job)
                    await asyncio.wait_for(process(),720)
                await run_in_threadpool(self.jobs.finish,job)
            except Exception as error:
                retry = not isinstance(error,AppError) or error.status_code >= 500 or error.status_code == 429
                await run_in_threadpool(self.jobs.finish,job,'Answer-sheet extraction could not finish. Your existing answers are saved.',retry,
                    isinstance(error,AppError) and error.code=='WORK_CAPACITY')
        return True
