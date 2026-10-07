import asyncio
import json
import unittest
from unittest.mock import patch
import httpx
from datetime import datetime, timezone
from uuid import uuid4
from langchain_core.messages import SystemMessage, HumanMessage
from app.langchain.profile_evaluator import LangChainProfileEvaluator, evaluation_payload
from app.langchain.llm import MentraLLM
from app.langchain.prompts import PromptSource, get_system_prompt
from app.student_profile.schemas import ProfileEvidence, ProfileContext, ProfileDetails, EvidenceInput, EvidenceItem, AIEvaluation
from app.student_profile.errors import EvaluationUnavailable
from testing.profile_evaluator import TestProfileEvaluator
from app.core.config import Settings
from app.langchain.model_factory import ModelFactory


class ProfileEvaluatorTests(unittest.TestCase):
    def fixture(self):
        details = ProfileDetails(education_level='primary', field_of_study='General studies', learning_goal='Understand nature',
            learning_preference='step_by_step', explanation_depth='brief')
        evidence = ProfileEvidence(id=str(uuid4()), learner_id=str(uuid4()), context_version=1, details_snapshot=details,
            input=EvidenceInput(source_type='assessment', source_id='assessment-1', occurred_at=datetime.now(timezone.utc), items=[
                EvidenceItem(id='a', dimension='reasoning', correct=True, difficulty=.3, prompt='Compare two objects'),
                EvidenceItem(id='b', dimension='reasoning', correct=False, difficulty=.6, prompt='Infer an ordering'),
            ]), created_at=datetime.now(timezone.utc))
        return evidence, ProfileContext(details=details, estimates={})

    def test_adapter_uses_factory_validated_schema_and_item_level_context(self):
        evidence, context = self.fixture()
        expected = asyncio.run(TestProfileEvaluator().evaluate(evidence, context))
        class Model:
            def with_structured_output(inner, schema, **options):
                self.assertIs(schema, AIEvaluation)
                self.assertEqual(options, {'method': 'function_calling'})
                return inner
            async def ainvoke(inner, messages):
                self.assertIsInstance(messages[0], SystemMessage)
                self.assertEqual(messages[0].content, get_system_prompt(PromptSource.STUDENT_PROFILE_EVALUATION))
                self.assertIsInstance(messages[1], HumanMessage)
                payload = json.loads(messages[1].content)
                self.assertEqual(payload, evaluation_payload(evidence, context))
                self.assertEqual([item['correct'] for item in payload['items']], [True, False])
                self.assertEqual([item['difficulty'] for item in payload['items']], [.3, .6])
                self.assertEqual(payload['assessment_context']['education_level'], 'primary')
                self.assertEqual(payload['deterministic_dimensions']['reasoning']['item_ids'], ['a', 'b'])
                return expected
        class Factory:
            def get_model(inner):
                return Model()
        actual = asyncio.run(LangChainProfileEvaluator(Factory()).evaluate(evidence, context))
        self.assertEqual(actual, expected)

    def test_chat_and_profile_share_distinct_registered_prompts(self):
        chat = get_system_prompt(PromptSource.CHAT)
        profile = get_system_prompt(PromptSource.STUDENT_PROFILE_EVALUATION)
        self.assertNotEqual(chat, profile)
        self.assertIn('supportive learning assistant', chat)
        self.assertIn('broad teaching readiness', profile)
        shared = MentraLLM(object())
        self.assertIs(LangChainProfileEvaluator(shared).llm, shared)
        with self.assertRaises(ValueError):
            get_system_prompt('untrusted_client_prompt')

    def test_adapter_rejects_invalid_structured_output_and_hides_provider_details(self):
        evidence, context = self.fixture()
        for output in (None, {'reasoning': {'value': 2, 'confidence': 1}}, 'not structured'):
            class Model:
                def with_structured_output(inner, *_args, **_kwargs):
                    return inner
                async def ainvoke(inner, _messages):
                    return output
            class Factory:
                def get_model(inner):
                    return Model()
            with self.assertRaises(EvaluationUnavailable):
                asyncio.run(LangChainProfileEvaluator(Factory()).evaluate(evidence, context))
        class UnavailableFactory:
            def get_model(inner):
                raise RuntimeError('Private provider details')
        with self.assertRaises(EvaluationUnavailable) as error:
            asyncio.run(LangChainProfileEvaluator(UnavailableFactory()).evaluate(evidence, context))
        self.assertNotIn('Private provider details', str(error.exception))

    def test_real_model_factory_and_langchain_tool_output_parse(self):
        """Exercise the actual SDK/tool schema/parser with controlled HTTP transport."""
        from langchain_openai import ChatOpenAI
        evidence, context = self.fixture()
        expected = asyncio.run(TestProfileEvaluator().evaluate(evidence, context))
        captured = []
        async def handler(request):
            body = json.loads(request.content)
            captured.append(body)
            tool = body['tools'][0]['function']
            self.assertEqual(set(tool['parameters']['properties']), {'overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity'})
            self.assertIn('primary', body['messages'][1]['content'])
            return httpx.Response(200, json={
                'id': 'synthetic-completion', 'object': 'chat.completion', 'created': 1, 'model': 'test-profile-model',
                'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
                    'tool_calls': [{'id': 'test-call', 'type': 'function', 'function': {'name': tool['name'], 'arguments': expected.model_dump_json()}}]}}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
            })
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                configuration = Settings(_env_file=None, ai_model='test-profile-model', ai_base_url='https://profile-test.invalid/v1', ai_api_key='test-only-key')
                shared_llm = MentraLLM(ModelFactory(configuration))
                with patch('langchain_openai.ChatOpenAI', side_effect=lambda **kwargs: ChatOpenAI(**kwargs, http_async_client=client)):
                    return await LangChainProfileEvaluator(shared_llm).evaluate(evidence, context)
        actual = asyncio.run(run())
        self.assertEqual(actual, expected)
        self.assertEqual(len(captured), 1)
