"""Opt-in configured-provider checks with synthetic inputs and no domain writes.

Run from the repository root with PYTHONPATH=backend. Uses the normal model factory.
"""
import asyncio
import json
import re
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage, ToolMessage

from app.chat.interactions import create_interaction_tools
from app.chat.response import ChatResponse
from app.core.config import settings
from app.history_management.budgets import ToolBudget
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.prompts import PromptSource


async def main():
    llm = MentraLLM(ModelFactory(settings))
    results = []
    scenarios = [
        ('custom_topic', 'Offer me three learning topics to choose from, and let me type my own topic inside the same card.', 'present_choices'),
        ('form', 'Before you plan my study session, collect my topic and how many minutes I have in one compact form.', 'request_input'),
        ('bars', 'Compare illustrative difficulty ratings of arrays, binary search and dynamic programming on a 1 to 5 scale using visual bars. Label the ratings as illustrative.', 'present_visuals'),
        ('direct', 'What is 2 + 2? Answer directly in one sentence.', None),
        ('icons', 'Give me one short reading tip and one short practice tip, each with an appropriate inline Lucide icon beside its text. Use no tools.', None),
    ]
    for name, request, expected in scenarios:
        scope = {'current_user_message_id': str(uuid4())}
        tools = create_interaction_tools('synthetic-ui-check', scope, ToolBudget())
        response = await asyncio.wait_for(llm.ainvoke_messages(PromptSource.CHAT, [HumanMessage(content=request)], tools=tools), 90)
        calls = response.tool_calls
        if expected is None:
            assert not calls, f'{name}: unnecessary interaction'
            if name == 'icons':
                assert isinstance(response.content, str) and len(re.findall(r':icon\[[A-Za-z][A-Za-z0-9-]{0,63}\]', response.content)) >= 2, 'Expected inline icon directives beside tip text'
        else:
            assert any(call['name'] == expected for call in calls), f'{name}: expected {expected}'
            by_name = {tool.name: tool for tool in tools}
            receipts = []
            for call in calls:
                receipt = await by_name[call['name']].ainvoke(call['args'])
                receipts.append(ToolMessage(content=json.dumps(receipt), tool_call_id=call['id']))
            cards = ChatResponse(content='', interactions=scope['interactions']).model_dump(mode='json')['interactions']
            if name == 'custom_topic':
                assert any(option.get('input') for card in cards for option in card.get('options', [])), 'Custom topic has no attached input'
            if name == 'bars':
                assert len(cards[0]['bars']) == 3
                continuation = await asyncio.wait_for(llm.ainvoke_messages(PromptSource.CHAT,
                    [HumanMessage(content=request), response, *receipts]), 90)
                assert continuation.content and not continuation.tool_calls, 'Static visuals must permit a normal explanation'
        results.append({'scenario': name, 'tools': [call['name'] for call in calls], 'passed': True, 'cards': scope.get('interactions', [])})
        print(f'{name}: passed', flush=True)
    path = Path('backend/.cache/chat-ui-live.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(results)} configured-provider UI checks passed; no domain records created.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
