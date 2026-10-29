"""One short structured background extraction, including the existing admission flags."""

from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from .validation import Admission


class CapturedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=500)
    category: Literal["fact", "goal", "preference"]
    evidence_quote: str = Field(min_length=1, max_length=1000)
    equivalent_memory_id: UUID | None = None
    admission: Admission
    action: Literal["create", "update", "reaffirm", "review", "skip"] = "create"
    target_memory_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    same_fact: bool = False
    change: Literal["enrichment", "correction", "change_over_time"] | None = None
    explicit_correction: bool = False

    @model_validator(mode="after")
    def target(self):
        if self.action in ("update", "reaffirm", "review") and (
            not self.target_memory_id or self.expected_revision is None
        ):
            raise ValueError(
                "Memory reconciliation needs a supplied target and its revision"
            )
        if self.action == "update" and (not self.same_fact or self.change is None):
            raise ValueError(
                "Updating a memory requires the same independently changeable fact"
            )
        if self.action == "reaffirm" and not self.same_fact:
            raise ValueError("Reaffirmation requires the same fact")
        if self.action == "create" and self.target_memory_id:
            raise ValueError("Creating a memory cannot identify an existing target")
        return self


class MemoryCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CapturedMemory] = Field(default_factory=list, max_length=6)
