"""Public response decisions, separate from domain authorization and execution."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

OutcomeState = Literal['completed', 'awaiting_input', 'in_progress', 'partial', 'failed', 'paused']


class RequestedTask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=80)
    state: OutcomeState = 'completed'
    receipt_ids: list[str] = Field(default_factory=list, max_length=20)
    required: bool = True
    operation: str | None = Field(default=None, max_length=80,
        description='Exact tool name for a requested operation; omit for direct teaching/text tasks. Completed operations require matching receipts.')
    grounding: Literal['none','study_material','web'] = Field(default='none',
        description='Required evidence for this deliverable. A source-only explanation cannot complete without the requested returned sources.')


class FinishResponse(BaseModel):
    """Finish the response honestly; enabled capabilities never require use.

    Include all requested tasks, referencing actual tool-call receipt IDs for
    operations. Ordinary answers need no receipt. queued/running work is
    in_progress, pending user input awaiting_input, unfinished work partial/failed.
    """
    model_config = ConfigDict(extra='forbid')
    content: str = ''
    conversation_title: str | None = Field(default=None, max_length=80)
    outcome: OutcomeState = 'completed'
    tasks: list[RequestedTask] = Field(default_factory=list, max_length=20)


class OutcomeControl(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['generation_retry', 'generation_resume', 'grading_retry']
    id: str
    revision: int


class ResponseOutcome(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = 3
    state: OutcomeState = 'completed'
    retryable: bool = False
    reason_code: str | None = None
    tasks: list[dict] = Field(default_factory=list, max_length=64)
    legacy: bool = False
    control_action: OutcomeControl | None = None

    @field_validator('tasks')
    @classmethod
    def public_tasks(cls, tasks):
        # Matching fingerprints belong only to private retained execution state.
        return [{key:value for key,value in task.items() if key not in ('signature','superseded_by')} for task in tasks]
