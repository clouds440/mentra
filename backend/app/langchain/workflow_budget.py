"""One cost/deadline envelope shared by nested model invocations."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from app.core.exceptions import AppError


@dataclass
class ModelBudget:
    deadline: float = field(default_factory=lambda: monotonic()+150)
    rounds: int = 0
    input_tokens: int = 0
    output_reserved: int = 0
    answer_reserve: float = 20

    @property
    def remaining(self):
        return max(0, self.deadline - monotonic())

    @property
    def tool_remaining(self):
        return max(.001, self.remaining - self.answer_reserve)

    def reserve(self, tokens, output):
        if monotonic() >= self.deadline or self.rounds >= 12 or self.input_tokens+tokens > 65536 or self.input_tokens+tokens+self.output_reserved+output > 98304:
            raise AppError('AI_WORKFLOW_BUDGET', 'The workflow reached its total model or time budget. Continue with a smaller request.', 422)
        self.rounds += 1
        self.input_tokens += tokens
        self.output_reserved += output


current_budget = ContextVar('mentra_model_budget', default=None)


@contextmanager
def model_budget(*, deadline=None):
    if current_budget.get() is not None:
        yield current_budget.get()
        return
    token = current_budget.set(ModelBudget(deadline=deadline) if deadline is not None else ModelBudget())
    try:
        yield current_budget.get()
    finally:
        current_budget.reset(token)
