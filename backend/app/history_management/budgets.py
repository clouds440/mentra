from dataclasses import dataclass, field
from app.core.exceptions import AppError
from langchain_core.messages import HumanMessage
from contextlib import contextmanager
from contextvars import ContextVar

_admitted = ContextVar('admitted_tool_budget', default=None)


@dataclass
class ToolBudget:
    calls: int = 0
    writes: int = 0
    result_characters: int = 0
    cache: dict = field(default_factory=dict)
    result_tokens: int = 0
    delivered: dict = field(default_factory=dict)
    max_calls: int = 6
    max_result_tokens: int = 3200
    max_result_bytes: int = 12800

    def call(self, write=False):
        if _admitted.get() is self:
            return  # The executor already counted this physical attempt.
        if write and (self.result_tokens > self.max_result_tokens - 256 or self.result_characters > self.max_result_bytes - 1024):
            raise AppError('TOOL_BUDGET', 'No space remains for a write receipt. Answer from available evidence.', 422)
        self.calls += 1
        self.writes += int(write)
        if self.calls > self.max_calls or self.writes > 2:
            raise AppError('TOOL_BUDGET', 'Tool call limit reached. Answer from available evidence.', 422)

    @contextmanager
    def admitted(self):
        token = _admitted.set(self)
        try:
            yield
        finally:
            _admitted.reset(token)

    def consume(self, content, *, reserve_tokens=0, reserve_bytes=0):
        # UTF-8 bytes bound byte-tokenized content even for CJK/emoji/code.
        size = len(content.encode('utf-8'))
        from app.langchain.token_policy import count_messages
        tokens = count_messages([HumanMessage(content=content)])
        if self.result_characters + size + reserve_bytes > self.max_result_bytes or self.result_tokens + tokens + reserve_tokens > self.max_result_tokens:
            raise AppError('TOOL_BUDGET', 'Tool result budget reached.', 422)
        self.result_characters += size
        self.result_tokens += tokens
