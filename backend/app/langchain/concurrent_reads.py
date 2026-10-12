"""Fetch independent reads together, publish their scope changes in call order."""
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic

from app.core.logging import workflow_logger

staging_reads = ContextVar('staging_tool_reads', default=False)


@dataclass(frozen=True)
class StagedRead:
    project: object
    payload: object

    def materialize(self):
        return self.project(self.payload)


def project_read(project, payload):
    return StagedRead(project, payload) if staging_reads.get() else project(payload)


async def gather_reads(actions, *, limit=4):
    """Bound fanout and drain cancelled siblings before leaving the caller's scope."""
    semaphore = asyncio.Semaphore(limit)

    async def run(action):
        started = monotonic()
        async with semaphore:
            workflow_logger.event('tool.queue', duration_ms=round((monotonic()-started)*1000, 3))
            return await action()

    tasks = [asyncio.create_task(run(action)) for action in actions]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
