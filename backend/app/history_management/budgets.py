from dataclasses import dataclass, field
from app.core.exceptions import AppError
from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately


@dataclass
class ToolBudget:
    calls: int = 0
    writes: int = 0
    result_characters: int = 0
    cache: dict = field(default_factory=dict)
    result_tokens: int = 0
    delivered: dict = field(default_factory=dict)

    def call(self, write=False):
        if write and (self.result_tokens > 2944 or self.result_characters > 11776):
            raise AppError('TOOL_BUDGET', 'No space remains for a write receipt. Answer from available evidence.', 422)
        self.calls += 1
        self.writes += int(write)
        if self.calls > 6 or self.writes > 2:
            raise AppError('TOOL_BUDGET', 'Tool call limit reached. Answer from available evidence.', 422)

    def consume(self, content):
        # UTF-8 bytes bound byte-tokenized content even for CJK/emoji/code.
        size = len(content.encode('utf-8'))
        from app.langchain.token_policy import count_messages
        tokens = count_messages([HumanMessage(content=content)])
        if self.result_characters + size > 12800 or self.result_tokens + tokens > 3200:
            raise AppError('TOOL_BUDGET', 'Tool result budget reached.', 422)
        self.result_characters += size
        self.result_tokens += tokens
