import unittest
from langchain_core.messages import AIMessageChunk, HumanMessage
from app.langchain.llm import MentraLLM
from app.langchain.prompts import PromptSource

class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_text_and_canonical_aggregation(self):
        class Model:
            async def astream(self, messages):
                yield AIMessageChunk(content='Hello ')
                yield AIMessageChunk(content='world')
        class Factory:
            def get_model(self): return Model()
        deltas=[]
        async def emit(value): deltas.append(value)
        reply=await MentraLLM(Factory()).ainvoke_messages(PromptSource.CHAT,[HumanMessage(content='Hi')],on_delta=emit)
        self.assertEqual(reply.content,'Hello world')
        self.assertEqual(''.join(deltas),'Hello world')

    async def test_tool_arguments_never_stream_and_preview_resets(self):
        class Model:
            async def astream(self,messages):
                yield AIMessageChunk(content='',tool_call_chunks=[dict(name='lookup',args='{"secret":"private"}',id='call1',index=0)])
        class Factory:
            def get_model(self):return Model()
        deltas=[]
        async def emit(value):deltas.append(value)
        reply=await MentraLLM(Factory()).ainvoke_messages(PromptSource.CHAT,[HumanMessage(content='Find')],on_delta=emit)
        self.assertEqual(deltas,[None])
        self.assertEqual(reply.tool_calls[0]['args'],{'secret':'private'})
