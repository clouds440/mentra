"""One cost/deadline envelope shared by nested model invocations."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from app.core.exceptions import AppError
from app.core.config import settings


def input_envelope():
    # A long but admitted context must be usable across the permitted rounds,
    # rather than hitting an unrelated smaller cumulative ceiling mid-answer.
    return max(131072, min(settings.chat_recovery_input_tokens,
        settings.chat_context_window_tokens-settings.chat_output_token_reserve-256)*12)


@dataclass
class ModelBudget:
    deadline: float = field(default_factory=lambda: monotonic()+settings.chat_turn_timeout_seconds)
    rounds: int = 0
    input_tokens: int = 0
    output_reserved: int = 0
    answer_reserve: float = 20
    max_rounds: int = 12
    max_input_tokens: int = field(default_factory=input_envelope)
    max_total_tokens: int = field(default_factory=lambda: max(196608,input_envelope()+settings.chat_output_token_reserve*12))

    @property
    def remaining(self):
        return max(0, self.deadline - monotonic())

    @property
    def tool_remaining(self):
        return max(.001, self.remaining - self.answer_reserve)

    def reserve(self, tokens, output):
        if monotonic() >= self.deadline or self.rounds >= self.max_rounds or self.input_tokens+tokens > self.max_input_tokens or self.input_tokens+tokens+self.output_reserved+output > self.max_total_tokens:
            raise AppError('AI_WORKFLOW_BUDGET', 'The workflow reached its total model or time budget. Continue with a smaller request.', 422)
        self.rounds += 1
        self.input_tokens += tokens
        self.output_reserved += output


current_budget = ContextVar('mentra_model_budget', default=None)


@contextmanager
def model_budget(*, deadline=None, **limits):
    if current_budget.get() is not None:
        yield current_budget.get()
        return
    token = current_budget.set(ModelBudget(**({'deadline': deadline} if deadline is not None else {}), **limits))
    try:
        yield current_budget.get()
    finally:
        current_budget.reset(token)
