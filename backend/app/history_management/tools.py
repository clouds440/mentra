from langchain_core.tools import StructuredTool
from .schemas import HistoryLookup, MemoryToolInput


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

    return [
        StructuredTool.from_function(name='history_lookup', description='Retrieve original past exchanges when relevant context is missing. Use message_id from a conversation summary to recover exact code or wording; continue with content_offset=next_content_offset for large messages. Otherwise search by keywords or sequence anchors. Summary references alone are not evidence. Cross-chat search requires keywords. Owner and current chat are server-bound.', args_schema=HistoryLookup, coroutine=history_lookup, metadata={'parallel_read': True}),
        StructuredTool.from_function(name='user_memory', description='Recall relevant saved user facts by keywords, or propose an evidence-backed durable memory. Writes need an exact quote and visible user-message ID. Never save secrets. Sensitive information requires explicit remember consent.', args_schema=MemoryToolInput, coroutine=user_memory, metadata={'parallel_read': True}),
    ]
