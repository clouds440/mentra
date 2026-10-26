"""Offline schema/context estimates; no provider or domain execution."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID
from langchain_core.messages import HumanMessage, SystemMessage
from app.langchain.history_orchestration import tool_reply
from app.langchain.planning import plan_request
from app.langchain.token_policy import schema_tokens, count_messages
from app.langchain.prompts import PromptSource, get_system_prompt
from app.chat.titles import NewChatReply


async def snapshot(query, first=False, *, web=None):
    captured = []
    plan = plan_request(query)
    class Captured(Exception):
        pass
    class Model:
        async def ainvoke_messages(self, source, messages, **kwargs):
            captured.append(kwargs)
            raise Captured  # Measure the request, never simulate successful execution.
    identity = str(UUID(int=1))
    scope = dict(current_user_message_id=identity, current_answer_text=query, conversation_id=identity, context_rows=[], history_references=[], memory_references=[],
        execution_plan=plan, history_token_budget=4096, learner_service=Mock(), rag_service=Mock(), assessment_service=Mock(), event_proposal_service=Mock())
    if web is not None:
        scope['web_search_service'] = web
    try:
        await tool_reply(Model(), [HumanMessage(content=query, id=identity)], SimpleNamespace(events=Mock()), identity, scope,
                         (PromptSource.CHAT_TITLE,) if first else (), {}, output_schema=NewChatReply if first else None)
    except Captured:
        pass
    arguments = captured[0]
    instructions = '\n\n'.join(get_system_prompt(source) for source in (PromptSource.CHAT, *arguments['additional_sources']))
    total = count_messages([SystemMessage(content=instructions + arguments['system_context']), HumanMessage(content=query)]) + schema_tokens(arguments['tools'])
    return dict(query=query, tools=[getattr(tool, 'name', getattr(tool, '__name__', '')) for tool in arguments['tools']],
                schema_tokens=schema_tokens(arguments['tools']), estimated_total_input=total)


if __name__ == '__main__':
    for query, first in [('Hello',False), ('Explain photosynthesis',False), ('What is my agenda tomorrow?',False), ('Give me a quiz',False), ('Hello',True)]:
        print(json.dumps(asyncio.run(snapshot(query, first))))
