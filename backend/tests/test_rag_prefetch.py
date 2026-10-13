import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from langchain_core.messages import AIMessage, ToolMessage
from app.core.exceptions import AppError
from app.langchain.chat_service import ChatService
from app.langchain.llm import MentraLLM
from app.langchain.orchestration_service import OrchestrationService
from app.rag.schemas import ChatSelection, RetrievalResult, RetrievedChunk, SourceReference


def passage():
    source = SourceReference(token='S1',document_id='doc',version_id='version',generation_id='generation',chunk_id='chunk',title='Library notes',heading_path=[],spans=[],excerpt='PRIVATE_PREFETCH_PASSAGE')
    return RetrievalResult(status='ok',context_ids=['context'],chunks=[RetrievedChunk(content=source.excerpt,score=1,score_type='test',source=source)])


class PrefetchTests(unittest.IsolatedAsyncioTestCase):
    async def run_chat(self, *, wants_rag=False, failure=False, drop_source=False):
        rag = Mock()
        calls = []
        def search(owner, request):
            calls.append(request)
            if failure:
                raise AppError('RAG_UNAVAILABLE','private retrieval failure',503)
            return RetrievalResult(status='no_eligible_sources') if drop_source and len(calls)>1 else passage()
        rag.search.side_effect=search
        scope=dict(conversation_id='chat',current_user_message_id='user',user_sequence=3,attachment_ids=[],context_rows=[dict(id='user',role='user',content='Refactor this source file')],history_references=[],memory_references=[],visible_ids=[],evidence_ids=set())
        rounds=[]
        class Model:
            def bind_tools(model, *args, **kwargs): return model
            async def ainvoke(model, messages, **kwargs):
                serialized=json.dumps([str(message.content) for message in messages])+str(kwargs.get('system_context'))
                rounds.append(serialized)
                if len(rounds)==1:
                    self.assertNotIn('PRIVATE_PREFETCH_PASSAGE',serialized)
                    self.assertNotIn('private retrieval failure',serialized)
                    self.assertEqual(scope.get('study_sources'),[])
                    self.assertFalse(scope.get('tool_warnings'))
                    if wants_rag:
                        return AIMessage(content='',tool_calls=[dict(name='search_study_material',args={'query':'Refactor this source file'},id='read')])
                    return AIMessage(content='Here is the refactored code.')
                receipts=[json.loads(message.content) for message in messages if isinstance(message,ToolMessage)]
                if failure:
                    self.assertTrue(scope.get('tool_warnings'))
                    return AIMessage(content='The requested Library passages could not be retrieved.')
                if drop_source:
                    self.assertNotIn('PRIVATE_PREFETCH_PASSAGE',serialized)
                    self.assertEqual(receipts[-1]['status'],'no_eligible_sources')
                    return AIMessage(content='The selected source is no longer available.')
                self.assertIn('PRIVATE_PREFETCH_PASSAGE',serialized)
                self.assertEqual(receipts[-1]['sources'][0]['token'],'S1')
                return AIMessage(content='Supported by the requested passage [[S1]].')
        result=await OrchestrationService(ChatService(MentraLLM(SimpleNamespace(get_model=lambda:Model()))),rag=rag).chat_reply([('user','Refactor this source file')],ChatSelection(),'owner',history_scope=scope)
        return result,calls,scope,rounds

    async def test_unused_successful_prefetch_is_not_context_or_citations(self):
        result,calls,scope,rounds=await self.run_chat()
        self.assertEqual(len(calls),1)
        self.assertEqual(len(rounds),1)
        self.assertEqual(result.sources,[])
        self.assertEqual(result.retrieval_status,'not_requested')
        self.assertIsNone(result.retrieval_warning)
        self.assertFalse(result.tool_warnings)
        self.assertEqual(scope['_tool_budget'].calls,0)

    async def test_unused_failed_prefetch_does_not_warn_model_or_user(self):
        result,_,scope,rounds=await self.run_chat(failure=True)
        self.assertEqual(len(rounds),1)
        self.assertFalse(result.tool_warnings)
        self.assertIsNone(result.retrieval_warning)
        self.assertEqual(result.retrieval_status,'not_requested')
        self.assertEqual(scope['_tool_budget'].calls,0)

    async def test_requested_tool_delivers_passages_and_citations(self):
        result,calls,scope,rounds=await self.run_chat(wants_rag=True)
        self.assertEqual(len(calls),2)
        self.assertEqual(len(rounds),2)
        self.assertEqual(result.citations,['S1'])
        self.assertEqual(result.retrieval_scope.context_ids,['context'])
        self.assertEqual(scope['_tool_budget'].calls,1)

    async def test_requested_tool_failure_reaches_agent(self):
        result,_,_,rounds=await self.run_chat(wants_rag=True,failure=True)
        self.assertEqual(len(rounds),2)
        self.assertTrue(result.tool_warnings)

    async def test_tool_revalidates_instead_of_delivering_stale_prefetch(self):
        result,calls,_,_=await self.run_chat(wants_rag=True,drop_source=True)
        self.assertEqual(len(calls),2)
        self.assertEqual(result.sources,[])
        self.assertEqual(result.retrieval_status,'no_eligible_sources')
