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
                from app.langchain.workflow_budget import model_budget
                from time import monotonic
                from .grading_progress import GRADING_TIMEOUT_SECONDS
                async def checkpoint(grades):
                    await run_in_threadpool(self.service.repository.checkpoint_grades, job, grades)
                with model_budget(deadline=monotonic()+GRADING_TIMEOUT_SECONDS, max_rounds=4,
                                  max_input_tokens=131072, max_total_tokens=196608):
                    grades = await asyncio.wait_for(self.service.workflows.grade(job, checkpoint=checkpoint), GRADING_TIMEOUT_SECONDS)
                await run_in_threadpool(self.service.repository.complete, job, grades)
                workflow_logger.event('assessment.results_ready', questions=len(grades.questions))
                execution.outcome = 'success'
            except Exception as error:
                execution.outcome = 'failed'
                from app.core.exceptions import AppError
                if not isinstance(error, AppError) or error.code != 'ATTEMPT_NOT_FOUND':
                    terminal = isinstance(error, TimeoutError) or isinstance(error, AppError) and error.code in (
                        'AI_CONTEXT_LIMIT', 'AI_WORKFLOW_BUDGET', 'ASSESSMENT_INVALID_GENERATION', 'ASSESSMENT_INVALID_GRADE')
                    message = ('Evaluation timed out. Your answers are saved; retry evaluation to continue.'
                        if isinstance(error, TimeoutError) else error.message if isinstance(error, AppError) and error.code == 'AI_CONTEXT_LIMIT' else None)
                    await run_in_threadpool(self.service.repository.fail, job, retry=not terminal, error=message)
                logging.getLogger('mentra').warning('Assessment grading failed (%s)', type(error).__name__)
                workflow_logger.event('assessment.grading_failed', error_type=type(error).__name__, error_code=getattr(error,'code',None))
            return True

async def serve():
    from app.db.database import init_db, get_session_factory
    from app.langchain.model_factory import ModelFactory
    from app.langchain.llm import MentraLLM
    from app.learner.factory import create_learner_engine
    from app.core.config import settings
    settings.database_role = 'worker'
    from .service import create_assessments
    import signal
    from app.core.logging import configure_logging
    configure_logging('assessment-worker')
    init_db()
    factory = ModelFactory(settings)
    llm = MentraLLM(factory)
    learner = create_learner_engine(llm)
    from app.rag.embedding_process import ProcessEmbeddingService
    from app.rag.qdrant_store import QdrantVectorStore
    from app.rag.factory import create_rag_service
    from app.student_profile.factory import create_student_profile_service
    from app.files.factory import create_files
    files = create_files()
    files.check_configuration()
    embedding = ProcessEmbeddingService(settings)
    vectors = QdrantVectorStore(settings, embedding)
    rag = create_rag_service(learner, embedding, vectors, files)
    profile = create_student_profile_service(factory, llm)
    worker = AssessmentWorker(create_assessments(get_session_factory(), llm, learner, rag, profile, files=files))
    from app.langchain.evidence_worker import ChatEvidenceWorker
    from app.langchain.repositories.evidence import ChatEvidenceRepository
    evidence_worker = ChatEvidenceWorker(ChatEvidenceRepository(get_session_factory()), worker.service.workflows.llm, worker.service.workflows.learner)
    stopping = asyncio.Event()
    for name in (signal.SIGTERM, signal.SIGINT): signal.signal(name, lambda *_:stopping.set())
    async def consume(consumer):
        while not stopping.is_set():
            try:
                processed = await consumer.run_once()
                if processed:
                    continue  # Drain ready jobs; idle polling must not throttle a busy queue.
            except Exception as error:
                logging.getLogger('mentra').warning('Worker queue unavailable (%s)', type(error).__name__)
            try: await asyncio.wait_for(stopping.wait(), 2)
            except asyncio.TimeoutError: pass
    # Independent queues share the process, not a serial scheduling bottleneck.
    from .generation_worker import AssessmentGenerationWorker
    from .evidence_worker import AssessmentEvidenceWorker
    try:
        await asyncio.gather(consume(worker), consume(evidence_worker), consume(AssessmentGenerationWorker(worker.service)),
            consume(AssessmentEvidenceWorker(worker.service)))
    finally:
        rag.close(); vectors.close(); embedding.close(); files.close()

if __name__ == '__main__': asyncio.run(serve())
