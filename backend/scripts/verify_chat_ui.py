"""Opt-in configured-provider UI checks, using actual selection/discovery contracts.

Run from repository root with PYTHONPATH=backend. Synthetic data; no domain writes.
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
from app.langchain.tool_selection import ToolSelection


async def main():
    llm = MentraLLM(ModelFactory(settings))
    results = []
    chart_example = None
    scenarios = [
        ('custom_topic', 'Offer me three learning topics to choose from, and let me type my own topic inside the same card.', 'present_choices'),
        ('form', 'Before you plan my study session, collect my topic and how many minutes I have in one compact form.', 'request_input'),
        ('bars', 'Compare illustrative difficulty ratings of arrays, binary search and dynamic programming on a 1 to 5 scale using one native multi-bar card. Label the ratings as illustrative.', 'present_visuals'),
        ('direct', 'What is 2 + 2? Answer directly in one sentence.', None),
        ('icons', 'Give me one short reading tip and one short practice tip, each with an appropriate inline Lucide icon beside its text. Use no tools.', None),
        ('chart', 'Show a Recharts bar chart comparing these exact study times: Algebra 20 minutes, Geometry 30 minutes. Add a brief explanation. No external lookups.', None),
        ('spanish_form', 'Antes de planear mi estudio, recoge el tema y los minutos disponibles en un formulario interactivo compacto.', 'request_input'),
        ('disclosure', 'Put a useful algebra hint in a collapsed disclosure, with the answer outside. This is an illustrative example, not a real assessment.', None),
        ('prose_only', 'Explain a simple learning sequence in two plain sentences. No diagrams, charts, cards, icons or special formatting.', None),
        ('color', 'Emphasize the phrase Needs review with exactly the custom hex color #F54927. Keep the rest plain. No external lookups.', None),
        ('mermaid', 'Explain a simple browser-request/server-response flow with a small Mermaid sequence diagram and one sentence.', None),
        ('clarification', "Help me learn something technical. I haven't picked a topic yet.", 'clarify'),
        ('chart_followup', 'Keep that same chart and change Algebra to 25 minutes. Geometry stays 30. No external lookups.', None),
        ('comparison', 'Compare React and Angular for animation libraries and forms. Use these illustrative 1-5 ratings: animation React 5 Angular 3; forms React 5 Angular 4. Use one native comparison card and briefly explain a benefit and a trade-off. No other lookups.', 'present_visuals'),
        ('icon_sources', 'Explain React and Angular in two short phrases, each with its logo using an icon URL or SVG path. They are not Lucide icon names. Use known public HTTPS icon assets or small SVG paths, no external lookups.', None),
        ('chart_colors', 'Draw one Recharts bar chart with React as the first series and Angular second. Metric A: React 20 Angular 15. Metric B: React 30 Angular 25. Choose distinct explicit colors for the two series. No external lookups.', None),
    ]
    for name, request, expected in scenarios:
        scope = {'current_user_message_id': str(uuid4()), 'execution_plan': SimpleNamespace(tool_names=[])}
        tools = create_interaction_tools('synthetic-ui-check', scope, ToolBudget())
        selection = ToolSelection(tools, DOMAINS, scope)
        discovery = selection.discovery()
        by_name = {tool.name: tool for tool in [*tools, discovery]}
        messages = [HumanMessage(content=request)]
        if name == 'chart_followup':
            assert chart_example
            from langchain_core.messages import AIMessage
            messages = [HumanMessage(content='Compare Algebra 20 minutes and Geometry 30 minutes in a Recharts bar chart.'), AIMessage(content=chart_example), *messages]
        seen = []
        rounds = []
        for iteration in range(5):
            sources = tuple(PromptSource('chat_ui_' + topic) for topic in UI_TOPICS if topic in scope.get('_ui_topics', ()))
            start = perf_counter()
            response = await asyncio.wait_for(llm.ainvoke_messages(PromptSource.CHAT, messages,
                tools=[*selection.selected(), discovery], additional_sources=sources), 90)
            rounds.append({'seconds': round(perf_counter() - start, 3), 'usage': response.usage_metadata,
                           'tools': [call['name'] for call in response.tool_calls], 'references': list(scope.get('_ui_topics', ()))})
            if not response.tool_calls:
                break
            messages.append(response)
            for call in response.tool_calls:
                assert call['name'] == discovery.name or call['name'] in selection.active, 'Called an unbound tool'
                seen.append(call['name'])
                receipt = await by_name[call['name']].ainvoke(call['args'])
                selection.complete(call['name'])
                messages.append(ToolMessage(content=json.dumps(receipt), tool_call_id=call['id']))
        else:
            raise AssertionError(f'{name}: unnecessary model loop')
        content = str(response.content)
        cards = ChatResponse(content='', interactions=scope.get('interactions', [])).model_dump(mode='json')['interactions']
        if expected == 'clarify':
            assert any(tool in seen for tool in ('present_choices', 'request_input')), 'Missing topic should use native clarification'
            assert 'enable_workflow_tools' not in seen
        elif expected:
            assert expected in seen, f'{name}: expected {expected}, got {seen}'
        else:
            assert not cards, f'{name}: unnecessary input card'
        if name == 'custom_topic':
            assert any(option.get('input') for card in cards for option in card.get('options', []))
        if name in ('custom_topic', 'form', 'spanish_form'):
            assert 'enable_workflow_tools' not in seen, 'Common UI must not need discovery'
        if name == 'bars':
            assert len(cards[0]['bars']) == 3 and content
        if name == 'icons':
            assert len(re.findall(r':icon\[[A-Za-z][A-Za-z0-9-]{0,63}\]', content)) >= 2
        if name in ('chart', 'chart_followup', 'chart_colors'):
            match = re.search(r'```recharts\s*\n(.*?)```', content, re.S)
            assert match, 'Expected a Recharts JSON fence'
            chart = json.loads(match[1]); assert chart['type'] == 'BarChart' and len(chart['data']) == 2, f'Chart contract mismatch: {chart}'
            scope['chart_spec'] = chart
            if name in ('chart', 'chart_colors'):
                chart_example = content
                assert 'charts' in scope.get('_ui_topics', ()), 'Advanced reference was not discovered'
            else:
                values = sorted(row[chart['series'][0]['dataKey']] for row in chart['data'])
                assert values == [25, 30], 'Follow-up changed the wrong values'
            if name == 'chart_colors':
                assert len(chart['series']) == 2 and all(item.get('color') for item in chart['series']), 'Missing series colors'
        if name == 'disclosure':
            assert ':::details' in content
            assert 'disclosures' in scope.get('_ui_topics', ())
        if name == 'color':
            assert re.search(r':color\[Needs review\]\{hex=["\']#F54927["\']\}', content)
            assert 'color' in scope.get('_ui_topics', ())
        if name == 'mermaid':
            assert '```mermaid' in content and 'accTitle:' in content and 'accDescr:' in content
        if name == 'comparison':
            bars = cards[0]['bars']
            assert len(bars) == 4 and all(bar.get('group') and bar.get('series') for bar in bars), 'Missing comparison structure'
            assert len({bar['group'] for bar in bars}) == 2 and len({bar['series'] for bar in bars}) == 2
            assert ':color[' in content, f'Comparison omitted useful semantic emphasis: {content}'
        if name == 'icon_sources':
            assert len(re.findall(r':icon\[(?:https://[^\]]+|[Mm][\d\s.,+\-][^\]]*)\]', content)) >= 2, 'Missing generic icon sources'
        if name in ('direct', 'prose_only', 'icons', 'mermaid'):
            assert not seen and len(rounds) == 1, f'{name}: unnecessary lookup'
        if name == 'prose_only':
            assert not any(marker in content for marker in ('```', ':icon[', ':color[', '::bar'))
        results.append({'scenario': name, 'tools': seen, 'rounds': rounds, 'passed': True, 'cards': cards,
                        **({'chart_spec': scope['chart_spec'], 'chart_expected_values': [25, 30] if name == 'chart_followup' else [20, 30]} if 'chart_spec' in scope else {})})
        print(f'{name}: passed, {len(rounds)} model rounds, tools={seen}', flush=True)
    path = Path('backend/.cache/chat-ui-live.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(results)} configured-provider UI checks passed; no domain records created.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
