"""Deterministic inference for browser tests; auth, persistence and RAG stay real."""
from langchain_core.messages import AIMessage


class TestEmbedding:
    model_name, model_version, dimension, max_tokens = 'browser-test', 'v1', 3, 512

    def token_count(self, text):
        return len(text.split()) + 2

    def query_token_count(self, text):
        return self.token_count(text)

    def embed_query(self, text):
        return [1., 0., 0.]

    def embed_documents(self, texts):
        return [[1., 0., 0.] for _ in texts]


class TestChatFactory:
    def get_model(self):
        return self

    async def ainvoke(self, messages):
        system = str(messages[0].content)
        if '"token": "S1"' in system:
            return AIMessage(content='The source explains Python decorators as reusable wrappers for functions. [[S1]]')
        return AIMessage(content='No supporting Library material was found. This is a general answer.')
