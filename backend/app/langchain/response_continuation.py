"""One bounded semantic decision only when a typed message follows a pause."""
import asyncio
from typing import Literal
from pydantic import BaseModel
from .prompts import PromptSource


class ContinuationDecision(BaseModel):
    action: Literal['continue', 'change', 'new']


async def is_continuation(llm, original, message) -> Literal['continue', 'change', 'new']:
    try:
        result = await asyncio.wait_for(llm.ainvoke(PromptSource.RESPONSE_CONTINUATION,
            {'paused_request': original[:4000], 'new_message': message}, output_schema=ContinuationDecision), 12)
        return result.action
    except Exception:
        # A classifier outage must never attach a new request to old side effects.
        return 'new'
