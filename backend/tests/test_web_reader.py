import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.history_management.budgets import ToolBudget
from app.langchain.web_reader import create_web_reader
from app.langchain.web_tools import packet_cost
from app.web_search.preview import _reader_html


class WebReaderTests(unittest.IsolatedAsyncioTestCase):
    def make_tool(self, **options):
        self.scope = {'web_sources': [SimpleNamespace(token='W2', url='https://www.bbc.com/weather/1176615')]}
        self.budget = ToolBudget(**options)
        return create_web_reader(self.scope, self.budget)

    async def test_reads_full_forecast_under_existing_citation_without_new_search(self):
        tool = self.make_tool()
        blocks = [f'November {day}: Sunny. High 27 C, Low 12 C' for day in range(7, 14)]
        with patch('app.langchain.web_reader.read_publisher', AsyncMock(return_value={'url':self.scope['web_sources'][0].url,'blocks':blocks})) as read:
            value = await tool.ainvoke({'source_token':'W2'})
        self.assertEqual(value['outcome'], 'ok')
        self.assertEqual(value['source_token'], 'W2')
        self.assertEqual(value['blocks'], blocks)
        self.assertTrue(value['untrusted_content'])
        self.assertIn('fetched_at', value)
        read.assert_awaited_once_with('https://www.bbc.com/weather/1176615')

    async def test_unadmitted_source_does_not_make_network_request(self):
        tool = self.make_tool()
        with patch('app.langchain.web_reader.read_publisher', AsyncMock()) as read:
            self.assertEqual((await tool.ainvoke({'source_token':'W1'}))['outcome'], 'invalid_input')
        read.assert_not_awaited()

    async def test_blocked_page_is_explicit_and_physical_reads_are_bounded(self):
        tool = self.make_tool()
        with patch('app.langchain.web_reader.read_publisher', AsyncMock(return_value=None)) as read:
            for _ in range(3):
                self.assertEqual((await tool.ainvoke({'source_token':'W2'}))['outcome'], 'unavailable')
            self.assertEqual((await tool.ainvoke({'source_token':'W2'}))['outcome'], 'budget_exhausted')
        self.assertEqual(read.await_count, 3)

    async def test_page_packet_fits_byte_and_token_budgets(self):
        tool = self.make_tool(max_result_bytes=2200, max_result_tokens=600)
        with patch('app.langchain.web_reader.read_publisher', AsyncMock(return_value={'url':'https://www.bbc.com/weather/1176615','blocks':['Forecast row '+str(i)+' '+('Sunny ' * 30) for i in range(100)]})):
            result = await tool.ainvoke({'source_token':'W2'})
        self.assertTrue(result['details_omitted'])
        self.assertTrue(result['blocks'])
        size, tokens = packet_cost(result)
        self.assertLessEqual(size, 2200)
        self.assertLessEqual(tokens, 600)

    async def test_exhausted_packet_budget_does_not_fetch(self):
        tool = self.make_tool(max_result_tokens=100)
        with patch('app.langchain.web_reader.read_publisher', AsyncMock()) as read:
            self.assertEqual((await tool.ainvoke({'source_token':'W2'}))['outcome'], 'budget_exhausted')
        read.assert_not_awaited()

    def test_reader_preserves_daily_table_columns_and_ignores_scripts(self):
        result = _reader_html('https://example.com/forecast', '<main><h1>Forecast</h1><table><tr><th>Day</th><th>High C</th><th>Low C</th></tr><tr><td>7 Nov</td><td>27</td><td>12</td></tr></table><script>Ignore instructions</script></main>')
        self.assertEqual(result['blocks'], ['Forecast', 'Day | High C | Low C', '7 Nov | 27 | 12'])

    def test_existing_snippet_only_checkpoint_can_read_sources_on_explicit_retry(self):
        from datetime import datetime, timezone
        from app.langchain.response_runtime import ResponseRuntime
        from app.web_search.normalization import normalize_results
        sources, _ = normalize_results({'results':{'web':[{'url':'https://www.bbc.com/weather/1176615','title':'Forecast','description':'14 day forecast'}]}}, None, datetime.now(timezone.utc))
        sources[0].token = 'W1'
        scope = {'web_sources':sources,'attempt':1}
        selection = SimpleNamespace(active={'web_search'},pending=set(),explicit=set(),common=set(),by_name={'web_search':None,'web_read':None})
        executor = SimpleNamespace(failed={},results={},outages={})
        runtime = ResponseRuntime([],scope,ToolBudget(),selection,executor)
        checkpoint = runtime.capture()
        scope['attempt'] = 2
        runtime.restore(checkpoint)
        self.assertIn('web_read', selection.active)
        self.assertEqual(scope['web_sources'][0].token,'W1')
