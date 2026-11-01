"""Manual configured-model effort check; replay public evidence, never dispatch web tools.

Run: python -m testing.web_effort_probe --turn-id <saved public-history turn UUID>
Only the optional evidence read touches PostgreSQL (read-only). No chat, quota or
memory records are written. Model API calls are real; search/research are fixtures.
"""
import argparse
import asyncio
import json
from time import perf_counter
from uuid import UUID, uuid4
from unittest.mock import patch
from langchain_core.messages import HumanMessage
from app.core.config import settings
from app.langchain.history_orchestration import tool_reply
from app.langchain.llm import MentraLLM
from app.langchain.model_factory import ModelFactory
from app.langchain.workflow_budget import model_budget
from app.web_search import WebSearchService, WebSource


class ReplaySearch(WebSearchService):
    def __init__(self, sources, *, namespace='search', empty_first=False):
        super().__init__(None, None, enabled=True, namespace=namespace)
        self.sources, self.calls, self.empty_first = sources, [], empty_first

    async def search(self, request, **_):
        self.calls.append(request)
        if self.empty_first and len(self.calls) == 1:
            return self.envelope('no_results')
        return self.envelope('ok', sources=self.sources).model_copy(update={
            'research_report': ('Source synthesis: examine frontier expansion, imperial institutions, '
                'changing military and fiscal systems, reform and nationalism, and the First World War. '
                'Distinguish the traditional decline framework from institutional transformation; '
                'avoid presenting a single inevitable-decline explanation as scholarly consensus.'
                if self.namespace == 'research' else None)})


def saved_evidence(turn_id):
    from sqlalchemy import text
    from app.db.database import get_engine
    with get_engine().connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        metadata = connection.execute(text('''SELECT a.metadata FROM chat_turn t
            JOIN chat_message a ON a.conversation_id=t.conversation_id AND a.sequence=t.assistant_sequence
            WHERE t.id=:id'''), dict(id=str(turn_id))).scalar_one()
    # The first five sources are enough for this replay, not a production source limit.
    return [WebSource.model_validate(source) for source in metadata['web_sources'][:5]]


async def evaluate(name, query, sources, *, empty_first=False, research=True):
    search = ReplaySearch(sources, empty_first=empty_first)
    if research:
        search.research = ReplaySearch(sources, namespace='research')
    scope = dict(current_user_message_id=str(uuid4()), user_sequence=1, context_rows=[],
        history_references=[], memory_references=[], web_search_service=search)
    provider = MentraLLM(ModelFactory(settings.model_copy(update={'ai_max_retries': 0})))
    rounds, usage = [], []
    class Model:
        async def ainvoke_messages(self, *args, **kwargs):
            result = await provider.ainvoke_messages(*args, **kwargs)
            rounds.append([dict(name=call['name'], **(dict(arguments=call['args']) if call['name'] != 'FinishResponse' else {}))
                for call in result.tool_calls])
            usage.append(result.usage_metadata or {})
            return result
    started = perf_counter()
    with model_budget(), patch('app.langchain.workflow_tools.create_workflow_tools', return_value=[]):
        result = await tool_reply(Model(), [HumanMessage(content=query)], None, 'synthetic-effort-check', scope, (), {})
    research_calls = len(search.research.calls) if research else 0
    if name == 'stable':
        passed = not search.calls and not research_calls
    elif name == 'deep':
        passed = research_calls == 1 and len(search.calls) <= 1 and sum(
            call['name'] == 'web_research' for batch in rounds for call in batch) == 1
    elif empty_first:
        passed = 2 <= len(search.calls) <= 3 and not research_calls
    else:
        passed = len(search.calls) <= 2 and not research_calls
    # The research fixture is deliberately a limited report, so honestly reporting
    # its missing evidence is acceptable; routing must not retry the paid tool.
    passed = passed and scope.get('response_outcome', {}).get('state') in (
        ('completed', 'partial') if name == 'deep' else ('completed',))
    if name == 'overview':
        passed = passed and '![' in result.content
    return dict(case=name, passed=passed, seconds=round(perf_counter()-started, 2),
        search_calls=len(search.calls), research_calls=research_calls, model_rounds=len(rounds), rounds=rounds,
        input_tokens=sum(item.get('input_tokens', 0) for item in usage),
        output_tokens=sum(item.get('output_tokens', 0) for item in usage),
        outcome=scope.get('response_outcome', {}).get('state'), answer_characters=len(result.content),
        **({'answer_tail': result.content[-700:]} if not passed else {}))


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--turn-id', type=UUID, required=True)
    parser.add_argument('--case', choices=('stable', 'overview', 'deep', 'missing'))
    args = parser.parse_args()
    sources = saved_evidence(args.turn_id)
    cases = [
        ('stable', 'Briefly explain how an empire differs from a nation-state. No web lookup needed.', {}),
        ('overview', 'Can you provide a detailed history of the Ottoman Empire, including its rise to power, major rulers, key events, cultural and political developments, and eventual decline? Please include any notable historical images or illustrations if available.', {}),
        ('deep', 'Research competing historical explanations of the Ottoman Empire\'s decline versus transformation. I want a thorough sourced investigation comparing accounts and their evidence, not just a general overview.', {}),
        ('missing', 'Find a sourced overview of the Ottoman Empire and historical images if available.', dict(empty_first=True, research=False)),
    ]
    results = []
    for name, query, options in cases:
        if args.case and name != args.case:
            continue
        result = await evaluate(name, query, sources, **options)
        results.append(result)
        print(json.dumps(result), flush=True)
    if not all(result['passed'] for result in results):
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
