from dataclasses import dataclass, field
from app.core.exceptions import AppError


@dataclass
class ToolBudget:
    calls: int = 0
    writes: int = 0
    result_characters: int = 0
    cache: dict = field(default_factory=dict)

    def call(self, write=False):
        self.calls += 1
        self.writes += int(write)
        if self.calls > 6 or self.writes > 2:
            raise AppError('TOOL_BUDGET', 'Tool call limit reached. Answer from available evidence.', 422)

    def consume(self, content):
        # UTF-8 bytes bound byte-tokenized content even for CJK/emoji/code.
        size = len(content.encode('utf-8'))
        if self.result_characters + size > 3000:
            raise AppError('TOOL_BUDGET', 'Tool result budget reached.', 422)
        self.result_characters += size
