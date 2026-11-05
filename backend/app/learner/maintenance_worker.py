"""Bounded organization runs after delivery with no open DB session during inference."""
import asyncio
from app.core.observability.timing import run_in_threadpool
from app.core.logging import workflow_logger


class LearnerMaintenanceWorker:
    def __init__(self, learner, admission=None):
        self.learner, self.admission = learner, admission

    async def run_once(self):
        repository = self.learner.repository
        job = await run_in_threadpool(repository.claim_maintenance)
        if not job: return False
        try:
            if job['kind'] != 'organization': raise ValueError('Unsupported maintenance kind')
            from app.db.admission import background_capacity
            async with background_capacity(self.admission, job['learner_id'], seconds=100):
                result = await asyncio.wait_for(self.learner.organize_learning_topics(
                    job['learner_id'], job['context_id']), 90)
            unresolved = result.get('unresolved', 0)
            # Do not spin forever on unavailable advice. Preserve ungrouped IDs;
            # a later publication or explicit organization can retry them.
            await run_in_threadpool(repository.finish_maintenance, job,
                failed=bool(unresolved), more=result.get('organized',0)>=10)
        except Exception as error:
            workflow_logger.event('learner.maintenance_failed', kind=job['kind'], error_type=type(error).__name__)
            await run_in_threadpool(repository.finish_maintenance, job, failed=True)
        return True
