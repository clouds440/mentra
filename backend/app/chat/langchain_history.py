"""Read the canonical transcript as LangChain messages without a second store.

Callers provide the authenticated owner. Writes go through ConversationService,
which preserves idempotency, ownership, sequence allocation and sync revisions.
"""
from starlette.concurrency import run_in_threadpool
from langchain_core.messages import HumanMessage, AIMessage


def as_messages(rows):
    return [HumanMessage(content=row['content'], id=row['id']) if row['role'] == 'user'
            else AIMessage(content=row['content'], id=row['id'])
            for row in rows if row['role'] in ('user', 'assistant')]


class ConversationHistoryReader:
    def __init__(self, repository):
        self.repository = repository

    def load(self, owner, conversation_id, *, through=None, limit=256):
        return as_messages(self.repository.context_rows(owner, conversation_id, through, limit))

    async def aload(self, owner, conversation_id, *, through=None, limit=256):
        rows = await run_in_threadpool(self.repository.context_rows, owner, conversation_id, through, limit)
        return as_messages(rows)
