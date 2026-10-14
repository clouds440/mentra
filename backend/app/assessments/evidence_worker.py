"""Learning updates never delay publication of assessment results."""
from starlette.concurrency import run_in_threadpool
from app.core.logging import workflow_logger
from .repositories.evidence import AssessmentEvidenceJobs
from .schemas import GradedAssessment, QuestionGrade


class AssessmentEvidenceWorker:
    def __init__(self, service):
        self.service = service
        self.jobs = AssessmentEvidenceJobs(service.repository)

    async def run_once(self):
        job = await run_in_threadpool(self.jobs.claim)
        if not job: return False
        with workflow_logger.workflow('assessment.learning_update', log_context=job['attempt'].get('log_context')) as execution:
            try:
                # Public outcome labels are server decoration, not model fields.
                grades = GradedAssessment(questions=[QuestionGrade.model_validate({key: value for key, value in grade.items()
                    if key in QuestionGrade.model_fields}) for grade in job['attempt']['grades']])
                await run_in_threadpool(self.jobs.complete, job,
                    lambda tx: self.service.workflows.evidence(job, grades, tx))
                execution.outcome = 'success'
            except Exception as error:
                execution.outcome = 'failed'
                await run_in_threadpool(self.jobs.fail, job)
                workflow_logger.event('assessment.learning_update_failed', error_type=type(error).__name__)
        return True
