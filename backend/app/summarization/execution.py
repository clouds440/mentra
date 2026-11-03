"""Common provider-call lifecycle; each domain retains its own prompt and limits."""
import asyncio
import random
from contextlib import asynccontextmanager

MAX_ATTEMPTS = 5
LEASE_SECONDS = 120


class SummaryDeferred(Exception):
    def __init__(self, until=None):
        super().__init__('Summary is already leased or changed during generation')
        self.until = until


def retry_delay(attempts):
    return min(300, 2**attempts) + random.random()


@asynccontextmanager
async def generation(admission=None, owner=None):
    from app.langchain.workflow_budget import current_budget
    token = current_budget.set(None)
    try:
        from app.db.admission import background_capacity
        try:
            async with background_capacity(admission,owner,seconds=60):
                async with asyncio.timeout(45):
                    yield
        except Exception as error:
            from app.core.exceptions import AppError
            if isinstance(error,AppError) and error.code == 'WORK_CAPACITY':
                from datetime import datetime,timezone,timedelta
                raise SummaryDeferred(datetime.now(timezone.utc)+timedelta(seconds=5)) from None
            raise
    finally:
        current_budget.reset(token)
