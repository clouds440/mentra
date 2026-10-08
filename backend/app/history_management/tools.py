import json
from langchain_core.tools import StructuredTool
from app.core.exceptions import AppError
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
        StructuredTool.from_function(name='history_lookup', description='Retrieve bounded past user/assistant exchanges. Cross-chat search requires keywords. The current chat and owner are bound by the server.', args_schema=HistoryLookup, coroutine=history_lookup),
        StructuredTool.from_function(name='user_memory', description='Recall relevant saved user facts by keywords, or propose an evidence-backed durable memory. Writes need an exact quote and visible user-message ID. Never save secrets. Sensitive information requires explicit remember consent.', args_schema=MemoryToolInput, coroutine=user_memory),
    ]
