import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from app.assessments.schemas import GeneratedAssessment, GeneratedAssessmentBatch
from app.langchain.assessment_payloads import generation_payload
from app.langchain.history_orchestration import tool_reply
from app.langchain.prompts import PromptSource, get_system_prompt, get_prompt_version
from app.langchain.provider_usage import CacheUsageMixin
from app.langchain.token_policy import log_usage


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.plan = [dict(number=i + 1, question_type='written', brief=f'Task {i}') for i in range(4)]
        self.shared = dict(topic='Mathematics', sources=[dict(token='S1', excerpt='Full source text')],
            learner_context=dict(concepts=[dict(mastery=None, estimate_confidence=0, knowledge_status='unknown')]),
            level=None, result_style='feedback')

    def test_full_batch_omits_duplicate_overview_and_inactive_revision(self):
        payload = generation_payload(shared=self.shared, plan=self.plan, offset=0, batch_size=4, prior=[])
        self.assertNotIn('assessment_overview', payload)
        self.assertNotIn('original_overview', payload)
        self.assertNotIn('revision_instructions', payload)
        self.assertNotIn('level', payload)
        self.assertEqual(payload['question_plan'], self.plan)
        self.assertEqual(payload['sources'], self.shared['sources'])
        self.assertEqual(payload['learner_context'], self.shared['learner_context'])

    def test_split_batches_keep_other_tasks_and_identical_shared_prefix(self):
        batches = [generation_payload(shared=self.shared, plan=self.plan, offset=i, batch_size=2, prior=[]) for i in (0, 2)]
        self.assertEqual([q['number'] for q in batches[0]['assessment_overview']], [3, 4])
        self.assertEqual([q['number'] for q in batches[1]['assessment_overview']], [1, 2])
        serialized = [json.dumps(p, ensure_ascii=False, separators=(',', ':')) for p in batches]
        self.assertEqual(*[s.split(',"assessment_overview":')[0] for s in serialized])

    def test_revision_preserves_full_batch_originals_without_private_answers(self):
        original = [dict(prompt=f'Original {i} ' + 'detail ' * 60, marks=2, difficulty=.5,
            concept_ids=['c'], options=[], model_answer='PRIVATE', rubric='PRIVATE') for i in range(4)]
        payload = generation_payload(shared=dict(self.shared, revision_instructions='Make easier'),
            plan=self.plan, offset=1, batch_size=2, prior=[], revision=dict(questions=original))
        self.assertEqual([item['prompt'] for item in payload['original_questions']], [q['prompt'] for q in original[1:3]])
        self.assertEqual([item['number'] for item in payload['original_overview']], [1, 4])
        self.assertTrue(all(item['truncated'] for item in payload['original_overview']))
        self.assertNotIn('PRIVATE', json.dumps(payload))

    def test_internal_schema_drops_paper_but_public_contract_keeps_it(self):
        schema = convert_to_openai_tool(GeneratedAssessmentBatch)
        self.assertNotIn('paper', schema['function']['parameters']['properties'])
        self.assertLess(len(json.dumps(schema)), len(json.dumps(convert_to_openai_tool(GeneratedAssessment))))
        self.assertIn('paper', GeneratedAssessment.model_fields)
        with self.assertRaises(ValidationError):
            GeneratedAssessmentBatch(title='Practice', questions=[], paper=None)


class PromptActivationTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_outline_uses_leaf_marks_without_duplicate_weights(self):
        from uuid import uuid4
        from app.assessments.schemas import AssessmentDesign, GenerationRequest
        from app.langchain.assessment_design import design_assessment
        outline = AssessmentDesign(title='Fractions', sections=[dict(title='Section A', part_marks=[99],
            questions=[dict(number=1, parts=[dict(path=['a'], marks=2, brief='Add fractions'),
                dict(path=['b'], marks=2, brief='Subtract fractions')])])])
        llm = SimpleNamespace(ainvoke=AsyncMock(return_value=outline))
        request = GenerationRequest(client_request_id=uuid4(), topic='Fractions', context_id='context',
            count=1, question_format='mock_paper', total_marks=4)
        plan, paper = await design_assessment(llm, request, [], None)
        self.assertEqual(paper.sections[0].part_marks, [])
        self.assertEqual([part['marks'] for part in plan], [2, 2])
        self.assertEqual(paper.total_marks, 4)

    async def test_discovery_adds_assessment_policy_and_final_round_retains_it(self):
        class Empty(BaseModel):
            pass
        scope = dict(current_user_message_id='u', user_sequence=3, history_references=[], memory_references=[],
            execution_plan=SimpleNamespace(tool_names=[], direct_candidate=False, steps=[]))
        async def lookup():
            scope['_tool_budget'].calls = scope['_tool_budget'].max_calls
            return dict(outcome='ok')
        tool = StructuredTool.from_function(name='assessment_lookup', description='Read assessment', args_schema=Empty, coroutine=lookup)
        rounds = []
        class Model:
            async def ainvoke_messages(self, source, messages, **kwargs):
                rounds.append(kwargs)
                if len(rounds) == 1:
                    return AIMessage(content='', tool_calls=[dict(id='discover', name='enable_workflow_tools', args=dict(tool_names=['assessment_lookup']))])
                if len(rounds) == 2:
                    return AIMessage(content='', tool_calls=[dict(id='read', name='assessment_lookup', args={})])
                return AIMessage(content='The question asks for an explanation.')
        with patch('app.langchain.workflow_tools.create_workflow_tools', return_value=[tool]), \
             patch('app.langchain.history_orchestration.count_tokens_approximately', side_effect=count_tokens_approximately), \
             patch('app.langchain.token_policy.count_messages', side_effect=count_tokens_approximately):
            result = await tool_reply(Model(), [HumanMessage(id='u', content='Explain the question')], None, 'owner', scope, (), {})
        self.assertEqual(len(rounds), 3)
        self.assertNotIn(PromptSource.CHAT_ASSESSMENT, rounds[0]['additional_sources'])
        self.assertIn(PromptSource.CHAT_ASSESSMENT, rounds[1]['additional_sources'])
        self.assertIn(PromptSource.CHAT_ASSESSMENT, rounds[2]['additional_sources'])
        self.assertIsNone(rounds[2]['tools'])
        self.assertTrue(result.content)

    def test_all_prompt_sources_have_versioned_instructions(self):
        for source in PromptSource:
            self.assertTrue(get_system_prompt(source))
            self.assertTrue(get_prompt_version(source))


class ProviderCacheTests(unittest.TestCase):
    def model(self):
        class CacheModel(CacheUsageMixin, ChatOpenAI):
            pass
        return CacheModel(model='test', api_key='test-only', base_url='http://unit.invalid/v1')

    def test_deepseek_cache_counters_survive_real_nonstreaming_adapter(self):
        result = self.model()._create_chat_result(dict(id='r', model='test',
            choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant', content='Answer'))],
            usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120, prompt_cache_hit_tokens=80, prompt_cache_miss_tokens=20)))
        message = result.generations[0].message
        self.assertEqual(message.usage_metadata['input_token_details']['cache_read'], 80)
        with patch('app.core.logging.workflow_logger.event') as event:
            log_usage(message, PromptSource.CHAT, 111)
        self.assertEqual(event.call_args.kwargs['cached_tokens'], 80)
        self.assertEqual(event.call_args.kwargs['uncached_tokens'], 20)
        self.assertEqual(event.call_args.kwargs['input_tokens'], 100)

    def test_streaming_and_zero_cache_hits_remain_observable(self):
        model = self.model()
        for hit in (0, 80):
            result = model._convert_chunk_to_generation_chunk(dict(choices=[], usage=dict(
                prompt_tokens=100, completion_tokens=20, total_tokens=120, prompt_cache_hit_tokens=hit)), AIMessageChunk, None)
            self.assertEqual(result.message.usage_metadata['input_token_details']['cache_read'], hit)

    def test_standard_usage_and_missing_cache_counts_are_preserved(self):
        result = self.model()._convert_chunk_to_generation_chunk(dict(choices=[], usage=dict(
            prompt_tokens=100, completion_tokens=20, total_tokens=120, prompt_tokens_details=dict(cached_tokens=30))), AIMessageChunk, None)
        self.assertEqual(result.message.usage_metadata['input_token_details']['cache_read'], 30)
        with patch('app.core.logging.workflow_logger.event') as event:
            log_usage(AIMessage(content='Answer'), PromptSource.CHAT, 111)
        self.assertNotIn('cached_tokens', event.call_args.kwargs)
        self.assertFalse(event.call_args.kwargs['usage_available'])
