"""Bounded, source-supported derived context; never personal evidence."""
import json
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from langchain_core.messages import HumanMessage
from app.core.config import settings
from app.langchain.token_policy import count_messages


class Support(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    revision: int = Field(ge=1)


class SummaryBlock(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=1600)
    supports: list[Support] = Field(min_length=1, max_length=8)


class MemorySummary(BaseModel):
    model_config = ConfigDict(extra='forbid')
    blocks: list[SummaryBlock] = Field(max_length=16)

    @model_validator(mode='after')
    def support_budget(self):
        if sum(len(b.supports) for b in self.blocks) > 24:
            raise ValueError('Use at most 24 supporting references in the overview.')
        return self


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)


def envelope(blocks, state='ready', revision=0):
    # Support IDs are server-side fences, never citation tokens or prompt overhead.
    return dict(state=state, content='\n'.join(b['text'] for b in blocks), revision=revision)


def fits(blocks, config=settings):
    value = encoded(envelope(blocks, 'updating', 999999999))
    return (len(value) <= config.memory_summary_max_characters
            and count_messages([HumanMessage(content=value)]) <= config.memory_summary_max_tokens)


def bounded(blocks, config=settings):
    result = []
    for block in blocks:
        if len(result) >= 16:
            break
        if fits([*result, block], config):
            result.append(block)
    return result
