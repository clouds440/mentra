"""Durable grading worker; model calls happen outside owner transactions."""
import asyncio
import logging

from app.core.logging import workflow_logger

@workflow_logger.connect_module(ignore=('run_once',))
class AssessmentWorker:
    def __init__(self, service): self.service = service
    async def run_once(self):
        from starlette.concurrency import run_in_threadpool
        job = await run_in_threadpool(self.service.repository.claim)
        if not job: return False
        with workflow_logger.workflow('assessment.grading', log_context=job.get('attempt', {}).get('log_context')) as execution:
            workflow_logger.event('job.claimed', job_id=str(job.get('id', job.get('turn_id', 'unknown'))), attempt=job.get('attempts', job.get('attempt', {}).get('worker_attempts', 1)) if isinstance(job.get('attempt'), dict) else job.get('attempts', job.get('attempt', 1)))
            try:
                grades = await asyncio.wait_for(self.service.workflows.grade(job), 90)
                await run_in_threadpool(self.service.repository.complete, job, grades,
                    lambda tx:self.service.workflows.evidence(job, grades, tx))
                execution.outcome = 'success'
            except Exception as error:
                execution.outcome = 'failed'
                from app.core.exceptions import AppError
                if not isinstance(error, AppError) or error.code != 'ATTEMPT_NOT_FOUND':
                    await run_in_threadpool(self.service.repository.fail, job)
                logging.getLogger('mentra').warning('Assessment grading failed (%s)', type(error).__name__)
            return True

async def serve():
    from app.db.database import init_db, get_session_factory
    from app.langchain.model_factory import ModelFactory
    from app.langchain.llm import MentraLLM
    from app.learner.factory import create_learner_engine
    from app.core.config import settings
    from .service import create_assessments
    import signal
    from app.core.logging import configure_logging
    configure_logging('assessment-worker')
    init_db()
    worker = AssessmentWorker(create_assessments(get_session_factory(), MentraLLM(ModelFactory(settings)), create_learner_engine()))
    from app.langchain.evidence_worker import ChatEvidenceWorker
    from app.langchain.repositories.evidence import ChatEvidenceRepository
    evidence_worker = ChatEvidenceWorker(ChatEvidenceRepository(get_session_factory()), worker.service.workflows.llm, worker.service.workflows.learner)
    stopping = asyncio.Event()
    for name in (signal.SIGTERM, signal.SIGINT): signal.signal(name, lambda *_:stopping.set())
    while not stopping.is_set():
        await worker.run_once()
        await evidence_worker.run_once()
        try: await asyncio.wait_for(stopping.wait(), 2)
        except asyncio.TimeoutError: pass

if __name__ == '__main__': asyncio.run(serve())
