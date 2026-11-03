import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.core.exceptions import AppError
from app.history_management.budgets import ToolBudget
from app.langchain.workflow_tools import create_workflow_tools
from app.langchain.orchestration_service import OrchestrationService
from app.rag.schemas import ChatSelection, RetrievedChunk, RetrievalResult, SourceReference


def source(number):
    return SourceReference(token=f'S{number}', document_id='document', version_id='version',
        generation_id='generation', chunk_id=f'chunk-{number}', title='Study notes', heading_path=[],
        spans=[], excerpt=('Relevant evidence. ' * 40) + str(number))


class RefinementTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeat_revalidates_instead_of_replaying_prefetched_source_packet(self):
        rag = Mock()
        def result(number):
            item = source(number)
            return RetrievalResult(status='ok', chunks=[RetrievedChunk(content=item.excerpt,
                score=1, score_type='test', source=item)])
        rag.search.side_effect = [result(1), result(2)]
        scope = dict(rag_service=rag, retrieval_selection=ChatSelection(mode='SOURCE_SPECIFIC',
            document_ids=['document']), _initial_search=('same query', result(3)))
        tool = create_workflow_tools('owner', scope, ToolBudget())[0]
        first = await tool.ainvoke({'query':'same query'})
        second = await tool.ainvoke({'query':'same query'})
        self.assertEqual(rag.search.call_count, 2)
        self.assertEqual(first['sources'][0]['token'], 'S1')
        self.assertEqual(second['sources'][0]['token'], 'S2')
        self.assertEqual([s.chunk_id for s in scope['study_sources']], ['chunk-1','chunk-2'])

    async def test_overlapping_lookups_reuse_excerpts_and_keep_citation_identity(self):
        rag = Mock()
        rag.search.return_value = RetrievalResult(status='ok', chunks=[
            RetrievedChunk(content=item.excerpt, score=1, score_type='test', source=item)
            for item in [source(1), source(2)]])
        selection = ChatSelection(mode='SOURCE_SPECIFIC', document_ids=['document'])
        scope = dict(rag_service=rag, retrieval_selection=selection, study_sources=[source(1)])
        budget = ToolBudget(max_calls=8, max_result_tokens=4800, max_result_bytes=19200)
        tool = create_workflow_tools('owner', scope, budget)[0]
        first = await tool.ainvoke({'query': 'first focused lookup'})
        self.assertEqual(first['sources'][0], dict(token='S1', already_provided=True))
        self.assertEqual(first['sources'][1]['excerpt'], source(2).excerpt)
        budget.consume(json.dumps(first))
        for index in range(3):
            receipt = await tool.ainvoke({'query': f'refinement {index}'})
            self.assertTrue(all(item['already_provided'] for item in receipt['sources']))
            budget.consume(json.dumps(receipt))
        self.assertEqual(len(scope['study_sources']), 2)
        self.assertLess(budget.result_characters, 2000)
        for call in rag.search.call_args_list:
            request = call.args[1]
            self.assertEqual(request.document_ids, ['document'])
            self.assertEqual((request.limit, request.token_budget), (3, 1000))

    async def test_preparation_delegates_budget_to_history_coordinator(self):
        for retrieval in [ChatSelection(mode='SOURCE_SPECIFIC', document_ids=['document']), None]:
            rag = Mock()
            rag.search.return_value = RetrievalResult(status='ok')
            chat = SimpleNamespace(reply=AsyncMock(return_value='Answer'))
            scope = dict(conversation_id='chat', current_user_message_id='user', context_rows=[], history_references=[], memory_references=[])
            await OrchestrationService(chat, rag=rag).chat_reply([('user', 'Explain this')], retrieval, 'owner', history_scope=scope)
            self.assertNotIn('_tool_budget', scope)
            self.assertEqual(scope['retrieval_selection'], retrieval or ChatSelection())
            chat.reply.assert_awaited_once()

    async def test_extraction_warnings_reach_new_and_repeated_tool_receipts(self):
        item = source(1)
        item.warnings = ['English OCR; verify equations.']
        rag = Mock()
        rag.search.return_value = RetrievalResult(status='ok', chunks=[
            RetrievedChunk(content=item.excerpt, score=1, score_type='test', source=item)])
        scope = dict(rag_service=rag, retrieval_selection=ChatSelection())
        tool = create_workflow_tools('owner', scope, ToolBudget())[0]
        for _ in range(2):
            receipt = await tool.ainvoke({'query': 'equation'})
            self.assertEqual(receipt['sources'][0]['warnings'], item.warnings)

    def test_extended_budget_still_rejects_oversized_results_and_ninth_call(self):
        budget = ToolBudget(max_calls=8, max_result_tokens=4800, max_result_bytes=19200)
        for _ in range(8): budget.call()
        with self.assertRaises(AppError): budget.call()
        with self.assertRaises(AppError): budget.consume('😀' * 5000)
