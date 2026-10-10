"""Model input selection is separate from immutable user-visible history."""
from langchain_core.messages import AIMessage, HumanMessage, trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from app.core.config import settings
from app.core.exceptions import AppError


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class HistoryContextPolicy:
    def __init__(self, max_tokens=None):
        # Independently configurable; this is an input safety budget, not a product history-count decision.
        self.max_tokens = int(max_tokens or settings.chat_history_token_budget)
        if self.max_tokens < 256:
            raise ValueError('CHAT_HISTORY_TOKEN_BUDGET must be at least 256')

    def select(self, rows, max_tokens=None):
        values = [HumanMessage(content=row['content']) if row['role'] == 'user' else AIMessage(content=row['content'])
                  for row in rows if row['role'] in ('user', 'assistant')]
        chosen = trim_messages(values, max_tokens=max_tokens if max_tokens is not None else self.max_tokens, token_counter=count_tokens_approximately,
                               strategy='last', start_on='human', allow_partial=False)
        # Current question must survive even when it exceeds the configured history allowance.
        if values and (not chosen or chosen[-1] is not values[-1]):
            chosen = [values[-1]]
        return [('user' if isinstance(message, HumanMessage) else 'assistant', str(message.content)) for message in chosen]

    def for_prompt(self, messages, system_text):
        from langchain_core.messages import SystemMessage
        available = settings.chat_context_window_tokens - settings.chat_output_token_reserve - 256 - count_tokens_approximately([SystemMessage(content=system_text)])
        current = next((content for role, content in reversed(messages) if role == 'user'), '')
        if available < count_tokens_approximately([HumanMessage(content=current)]):
            raise AppError('CHAT_CONTEXT_LIMIT', 'The selected sources and question exceed the configured model context budget. Choose fewer sources or shorten the question.', 422)
        return self.select([dict(role=role, content=content) for role, content in messages], max_tokens=min(self.max_tokens, available))
