from langchain_core.tools import StructuredTool
from .schemas import HistoryLookup, MemoryToolInput, ConversationSummarySearch


def create_history_tools(service, owner, scope, budget):
    async def history_lookup(**kwargs):
        budget.call()
        body = HistoryLookup(**kwargs)
        key = 'history:' + body.model_dump_json()
        if key not in budget.cache:
            budget.cache[key] = await service.lookup(owner, scope, body, budget)
        return budget.cache[key]

    async def user_memory(**kwargs):
        body = MemoryToolInput(**kwargs)
        budget.call(body.action != 'recall')
        if body.action == 'recall':
            key = 'recall:' + body.model_dump_json()
            if key not in budget.cache:
                budget.cache[key] = await service.memory(owner, scope, body, budget)
            return budget.cache[key]
        result = await service.memory(owner, scope, body, budget)
        for key in list(budget.cache):
            if key.startswith('recall:'):
                budget.cache.pop(key)
        return result

    async def conversation_summary_search(**kwargs):
        budget.call()
        body = ConversationSummarySearch(**kwargs)
        # Explicit searches revalidate published content and live ownership.
        # Unchanged prompt-context payload caches remain revision based.
        return await service.search_summaries(owner, scope, body)

    return [
        StructuredTool.from_function(name='history_lookup', description='Retrieve original past exchanges when relevant context is missing. Use message_id from a conversation summary to recover exact code or wording; for another chat also set scope=selected_chats and chat_ids to its returned conversation ID. Continue with content_offset=next_content_offset for large messages. Otherwise search by keywords, or use sequence anchors within current_chat. Summary references alone are not evidence. Cross-chat search requires keywords or an exact message_id in selected_chats. Owner and current chat are server-bound.', args_schema=HistoryLookup, coroutine=history_lookup, metadata={'parallel_read': True}),
        StructuredTool.from_function(name='user_memory', description='Recall relevant saved user facts by keywords, or propose an evidence-backed durable memory. Writes need an exact quote and visible user-message ID. Never save secrets. Sensitive information requires explicit remember consent.', args_schema=MemoryToolInput, coroutine=user_memory, metadata={'parallel_read': True}),
        StructuredTool.from_function(name='conversation_summary_search', description='Search summaries and titles of this user\'s other saved conversations by specific keywords. The current chat summary is supplied separately when available. Returns up to three summaries with conversation IDs and coverage flags. Continue with offset=next_offset and the same query for more matches. Summaries are lossy, not evidence: use history_lookup with selected_chats and keywords or a referenced message_id to recover originals. Chats without summaries remain searchable with history_lookup. Owner and current chat are server-bound.', args_schema=ConversationSummarySearch, coroutine=conversation_summary_search, metadata={'parallel_read': True}),
    ]
