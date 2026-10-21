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
async def generation():
    from app.langchain.workflow_budget import current_budget
    token = current_budget.set(None)
    try:
        async with asyncio.timeout(45):
            yield
    finally:
        current_budget.reset(token)
