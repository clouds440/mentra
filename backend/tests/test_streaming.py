import unittest
from langchain_core.messages import AIMessageChunk, HumanMessage
from app.langchain.llm import MentraLLM
from app.langchain.prompts import PromptSource

class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_raw_provider_tool_markup_split_across_chunks_never_streams(self):
        import asyncio
        from app.langchain.provider_protocol import ProviderProtocolError
        class Model:
            async def astream(self, messages):
                yield AIMessageChunk(content='<')
                await asyncio.sleep(.21)
                for text in ('｜', '｜DS', 'ML｜｜ ', 'calls>', '<｜｜DSML｜｜ invoke name="conversation_summary_search">', 'x'*600):
                    yield AIMessageChunk(content=text)
        class Factory:
            def get_model(self): return Model()
        deltas = []
        async def emit(value): deltas.append(value)
        with self.assertRaises(ProviderProtocolError):
            await MentraLLM(Factory()).ainvoke_messages(PromptSource.CHAT, [HumanMessage(content='Find')], on_delta=emit)
        self.assertEqual(deltas, [None])

    async def test_raw_nonstreaming_tool_markup_is_rejected_but_documented_code_is_allowed(self):
        from langchain_core.messages import AIMessage
        from app.langchain.provider_protocol import ProviderProtocolError
        class Model:
            value = '<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="lookup">'
            async def ainvoke(self, messages): return AIMessage(content=self.value)
        model = Model()
        class Factory:
            def get_model(self): return model
        llm = MentraLLM(Factory())
        with self.assertRaises(ProviderProtocolError):
            await llm.ainvoke_messages(PromptSource.CHAT, [HumanMessage(content='Find')])
        model.value = 'Example syntax:\n```xml\n<｜｜DSML｜｜ calls>\n```'
        reply = await llm.ainvoke_messages(PromptSource.CHAT, [HumanMessage(content='Explain the syntax')])
        self.assertEqual(reply.content, model.value)

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
