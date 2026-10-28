import asyncio
from types import MethodType
from testing.legacy_event_capture import capture as legacy_capture
import unittest
from unittest.mock import AsyncMock, Mock, patch
from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from testing.postgres import PostgresSandbox
from testing.identities import learner_id
from app.chat.schemas import SendTurn
from app.chat.repositories.postgres import ChatRepository
from app.history_management.events.factory import create_events_service
from app.history_management.events.proposal_service import create_event_proposals
from testing.legacy_event_capture import EventCapture, event_candidate
from testing.legacy_keyword_policy import plan_request


class EventCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
    @classmethod
    def tearDownClass(cls): cls.db.close()

    def setup_capture(self, text='I have a quiz tomorrow 9 am. The quiz is about LLM Architecture and Training.'):
        owner = learner_id('alice')
        chats = ChatRepository(self.db.sessions)
        job = chats.begin_turn(owner, SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content=text, timezone='Asia/Karachi'))
        source = chats.context_rows(owner, job['conversation_id'], job['user_sequence'])[-1]
        scope = dict(job, context_rows=[source], current_user_message_id=source['id'], evidence_ids={source['id']})
        llm = AsyncMock()
        date = (source['created_at'].astimezone(ZoneInfo('Asia/Karachi'))+timedelta(days=1)).date()
        llm.ainvoke.return_value = EventCapture(practice_requested=False, events=[dict(quote=text, candidate=dict(title='LLM Architecture and Training quiz', kind='quiz', timezone='Asia/Karachi', starts_at=f'{date}T09:00:00+05:00'), admission=dict(supported=True, first_party=True, actual_event=True, complete_unambiguous=True, timezone_supported=True, confidence=.99))])
        service = create_event_proposals(self.db.sessions, create_events_service(self.db.sessions), llm)
        service.capture = MethodType(legacy_capture,service)
        return owner, service, llm, scope

    def test_announcement_saved_without_agent_call_and_replayed_without_paid_call(self):
        owner, service, llm, scope = self.setup_capture()
        with patch.object(service.graph, 'prepare', wraps=service.graph.prepare) as prepare:
            result = asyncio.run(service.capture(owner, scope))
        prepare.assert_not_called()  # Automatic admission needs no unused UI pause.
        self.assertEqual(result[0]['outcome'], 'saved')
        self.assertEqual(result[0]['event']['kind'], 'quiz')
        self.assertEqual(result[0]['event']['starts_at'].astimezone(ZoneInfo('Asia/Karachi')).hour, 9)
        self.assertEqual(llm.ainvoke.call_args.args[1]['account_timezone'], 'Asia/Karachi')
        replay = asyncio.run(service.capture(owner, scope))
        self.assertEqual(replay[0]['event']['id'], result[0]['event']['id'])
        self.assertEqual(llm.ainvoke.call_count, 1)

    def test_semantic_rejection_does_not_create_personal_event(self):
        owner, service, llm, scope = self.setup_capture('For example: I have a quiz tomorrow at 9 am.')
        llm.ainvoke.return_value = EventCapture(practice_requested=False, events=[])
        self.assertEqual(asyncio.run(service.capture(owner, scope)), [])

    def test_missing_timezone_or_uncertainty_leaves_reviewable_proposal(self):
        owner, service, llm, scope = self.setup_capture()
        item = llm.ainvoke.return_value.events[0]
        item.candidate.timezone = None
        item.candidate.starts_at = None
        item.admission.complete_unambiguous = False
        item.admission.timezone_supported = False
        result = asyncio.run(service.capture(owner, scope))
        self.assertEqual(result[0]['outcome'], 'awaiting_confirmation')

    def test_live_provider_separate_date_and_clock_format_saves(self):
        owner, service, llm, scope = self.setup_capture()
        item = llm.ainvoke.return_value.events[0]
        item.candidate.local_date = item.candidate.starts_at[:10]
        item.candidate.starts_at = '09:00'
        result = asyncio.run(service.capture(owner, scope))
        self.assertEqual(result[0]['outcome'], 'saved')
        event = result[0]['event']
        self.assertIsNone(event['local_date'])
        self.assertEqual(event['starts_at'].astimezone(ZoneInfo('Asia/Karachi')).hour, 9)

    def test_normalization_leaves_dst_gaps_folds_and_conflicting_dates_for_review(self):
        from app.history_management.events.capture import normalize_candidate
        from app.history_management.events.proposals import EventCandidate
        for day, clock in [('2026-11-01','01:30'), ('2026-03-08','02:30')]:
            item = EventCandidate(title='Exam', timezone='America/New_York', local_date=day, starts_at=clock)
            self.assertEqual(normalize_candidate(item), item)
        item = EventCandidate(title='Exam', timezone='Asia/Karachi', local_date='2026-10-14', starts_at='2026-10-15T09:00:00+05:00')
        self.assertEqual(normalize_candidate(item), item)

    def test_general_event_types_use_same_candidate_pipeline(self):
        for kind in ('assessment', 'assignment', 'quiz', 'test', 'exam', 'project', 'presentation', 'viva'):
            text = f'I have a {kind} tomorrow at 9 am.'
            self.assertTrue(event_candidate(text))
            plan = plan_request(text)
            self.assertIn('event_manage', plan.tool_names)
            self.assertNotIn('assessment_generate', plan.tool_names)
        self.assertFalse(event_candidate('Explain next token prediction'))
        self.assertIn('assessment_generate', plan_request('I have a quiz tomorrow. Give me an interactive practice quiz.').tool_names)
        for text in ('I have a quiz tomorrow. Do not give me practice questions.', 'I have a quiz tomorrow. Explain what a quiz means.'):
            self.assertNotIn('assessment_generate', plan_request(text).tool_names)

    def test_orchestration_does_not_launch_a_keyword_capture_prepass(self):
        from types import SimpleNamespace
        from app.langchain.orchestration_service import OrchestrationService
        owner, service, _, scope = self.setup_capture()
        scope.update(history_references=[],memory_references=[],visible_ids=[])
        service.capture = AsyncMock(side_effect=AssertionError('No pre-model event extraction'))
        chat = SimpleNamespace(reply=AsyncMock(return_value='A normal conversation response.'))
        response=asyncio.run(OrchestrationService(chat,history=SimpleNamespace(events=service.events,profile=None),event_proposals=service)
            .chat_reply([('user',scope['context_rows'][0]['content'])],None,owner,history_scope=scope))
        service.capture.assert_not_awaited()
        self.assertEqual(response.event_references,[])

    def test_disabled_auto_capture_has_no_model_cost(self):
        owner, service, llm, scope = self.setup_capture()
        service.events.preferences = Mock(return_value=dict(automatic_events=False, timezone=None))
        self.assertEqual(asyncio.run(service.capture(owner, scope)), [])
        llm.ainvoke.assert_not_called()

    def test_partial_capture_retains_saved_event_and_serializes_failure(self):
        owner, service, llm, scope = self.setup_capture()
        llm.ainvoke.return_value.events.append(llm.ainvoke.return_value.events[0].model_copy())
        service.admit = AsyncMock(side_effect=[dict(outcome='saved', event=dict(id='saved')), TimeoutError()])
        result = asyncio.run(service.capture(owner, scope))
        self.assertEqual(result[0]['event']['id'], 'saved')
        self.assertEqual(result[1]['outcome'], 'unavailable')
        self.assertEqual(result[1]['effect_certainty'], 'unknown')

    def test_capture_propagates_lifecycle_errors(self):
        from app.core.exceptions import AppError
        owner, service, _, scope = self.setup_capture()
        service.admit = AsyncMock(side_effect=AppError('CHAT_STALE_ATTEMPT', 'Stopped.', 409))
        with self.assertRaises(AppError):
            asyncio.run(service.capture(owner, scope))

    def test_automatic_gate_propagates_stale_claim(self):
        from app.core.exceptions import AppError
        from unittest.mock import patch
        owner, service, _, scope = self.setup_capture()
        with patch.object(service.repository, 'claim', side_effect=AppError('CHAT_STALE_ATTEMPT', 'Stopped.', 409)):
            with self.assertRaises(AppError):
                asyncio.run(service.capture(owner, scope))

    def test_failure_warning_accepts_typed_receipt(self):
        from app.langchain.tool_execution import failure, remember_failure
        scope = {}
        remember_failure(scope, 'event_manage', failure(TimeoutError(), write=True))
        self.assertEqual(scope['tool_warnings'][0]['effect_certainty'], 'unknown')
