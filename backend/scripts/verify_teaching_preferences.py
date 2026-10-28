"""Opt-in configured-model teaching-policy acceptance; synthetic input, no domain writes.

Run from repository root with PYTHONPATH=backend. Outputs a local evidence report.
"""
import asyncio
import json
import re
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import HumanMessage, ToolMessage
from app.chat.interactions import create_interaction_tools
from app.chat.response import ChatResponse
from app.core.config import settings
from app.history_management.budgets import ToolBudget
from app.langchain.capabilities import DOMAINS
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.prompts import PromptSource
from app.langchain.prompts.chat_ui import UI_TOPICS
from app.langchain.response_style import teaching_policy
from app.langchain.tool_selection import ToolSelection
from app.student_profile.schemas import ProfileDetails


async def main():
    llm = MentraLLM(ModelFactory(settings))
    results = []
    scenarios = [
        ('interactive_examples', 'Teach me what a doubling function is. Help me work through it.', dict(learning_preference='examples_first', participation='interactive'), 'activity'),
        ('mostly_explanations', 'Explain what a doubling function is.', dict(participation='mostly_explanations'), 'prose'),
        ('simple_fact', 'What is 7 times 8?', dict(participation='interactive', visual_support='prefer_visuals'), 'fact'),
        ('explicit_explanation', 'Explain a doubling function fully in prose. Do not ask questions or give me exercises.', dict(participation='interactive', visual_support='prefer_visuals'), 'prose'),
        ('prefer_visuals', 'Explain the sequence of steps from typing a webpage URL to seeing the page.', dict(visual_support='prefer_visuals'), 'diagram'),
        ('mostly_text', 'Explain the sequence of steps from typing a webpage URL to seeing the page.', dict(visual_support='mostly_text', participation='mostly_explanations'), 'prose'),
        ('explicit_diagram', 'Show a Mermaid flowchart for typing a URL, receiving HTML and rendering the page.', dict(visual_support='mostly_text'), 'diagram'),
        ('brief', 'Explain why dividing by a fraction means multiplying by its reciprocal.', dict(explanation_depth='brief', participation='mostly_explanations'), 'prose'),
        ('detailed', 'Explain why dividing by a fraction means multiplying by its reciprocal.', dict(explanation_depth='deep', participation='mostly_explanations'), 'prose'),
        ('goal_scope', 'What is the capital of France?', dict(learning_purpose='exam', learning_goal='Prepare for a quantum physics exam'), 'fact'),
    ]
    for name, request, overrides, expected in scenarios:
        details = ProfileDetails.model_validate(dict(education_level='undergraduate', field_of_study='General studies', learning_goal='Understand new concepts', learning_preference='balanced', explanation_depth='standard') | overrides)
        profile = dict(details=details.model_dump(mode='json'))
        context = json.dumps(dict(student_profile=profile, response_style=teaching_policy(profile)), separators=(',', ':'))
        scope = dict(current_user_message_id=str(uuid4()), execution_plan=SimpleNamespace(tool_names=[]))
        tools = create_interaction_tools('synthetic-teaching-check', scope, ToolBudget())
        selection = ToolSelection(tools, DOMAINS, scope)
        discovery = selection.discovery()
        by_name = {tool.name: tool for tool in [*tools, discovery]}
        messages = [HumanMessage(content=request)]
        rounds = []
        for _ in range(5):
            sources = tuple(PromptSource('chat_ui_' + topic) for topic in UI_TOPICS if topic in scope.get('_ui_topics', ()))
            start = perf_counter()
            response = await asyncio.wait_for(llm.ainvoke_messages(PromptSource.CHAT, messages,
                tools=[*selection.selected(), discovery], system_context=context, additional_sources=sources), 90)
            rounds.append(dict(seconds=round(perf_counter() - start, 3), usage=response.usage_metadata,
                               content=response.content, tools=[call['name'] for call in response.tool_calls]))
            if not response.tool_calls:
                break
            messages.append(response)
            for call in response.tool_calls:
                assert call['name'] == discovery.name or call['name'] in selection.active, 'Unbound tool'
                receipt = await by_name[call['name']].ainvoke(call['args'])
                rounds[-1].setdefault('receipts', []).append(receipt)
                selection.complete(call['name'])
                messages.append(ToolMessage(content=json.dumps(receipt), tool_call_id=call['id']))
        else:
            raise AssertionError(f'{name}: excessive loop')
        content = str(response.content)
        cards = ChatResponse(content='', interactions=scope.get('interactions', [])).model_dump(mode='json')['interactions']
        result = dict(scenario=name, rounds=rounds, cards=cards, content=content, words=len(content.split()), policy=teaching_policy(profile))
        results.append(result)
        Path('.cache').mkdir(exist_ok=True)
        Path('.cache/teaching-policy-live.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        if expected == 'activity':
            assert cards and any(card['kind'] in ('single_choice', 'multi_choice', 'text_input', 'form', 'questionnaire') for card in cards), f'{name}: no native participation: {content}'
            assert 'doubl' in content.lower(), f'{name}: activity omitted the teaching explanation'
            assert 'enable_workflow_tools' not in [tool for turn in rounds for tool in turn['tools']], 'Common activity required discovery'
        else:
            assert not cards, f'{name}: unwanted activity'
        if expected == 'diagram':
            assert '```mermaid' in content, f'{name}: no useful flow diagram'
        if expected in ('prose', 'fact'):
            assert not re.search(r'```(?:mermaid|recharts)|::bar', content), f'{name}: unwanted visual'
            assert not re.search(r'\b(?:would you like|shall we|want me to|your turn|try this yourself)\b', content, re.I), f'{name}: unwanted follow-up'
        if expected == 'fact':
            assert len(rounds) == 1 and len(content.split()) < 35
        print(f'{name}: passed ({len(rounds)} model rounds, {len(content.split())} words)', flush=True)
    sizes = {item['scenario']: item['words'] for item in results}
    assert sizes['detailed'] > sizes['brief'] * 1.4, f'Detail setting had little effect: {sizes}'
    print(f'All {len(results)} teaching scenarios passed. No domain records created.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
