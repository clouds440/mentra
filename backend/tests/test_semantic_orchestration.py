"""Semantic decisions, receipt truthfulness and business-result recovery."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from app.langchain.decision_schemas import FinishResponse, ResponseOutcome
from app.langchain.history_orchestration import tool_reply
from app.langchain.task_outcomes import finalize, record_receipt
from app.langchain.tool_selection import ToolSelection
from app.history_management.budgets import ToolBudget
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


def scope():
    return dict(current_user_message_id=str(uuid4()), conversation_id=str(uuid4()), user_sequence=1,
                history_references=[], memory_references=[], visible_ids=[], evidence_ids=set(), context_rows=[])


class OutcomeTests(unittest.TestCase):
    def test_synthesis_failure_preserves_native_results_without_another_model_call(self):
        from app.langchain.recovery_receipts import partial_response
        value=scope()
        self.assertIsNone(partial_response(value,'AI_PROVIDER_ERROR'))
        identifier=str(uuid4())
        value['assessment_cards']=[dict(generation_job_id=identifier)]
        record_receipt(value,dict(id='queued',name='assessment_generate',args={}),
            dict(outcome='queued',generation_job_id=identifier))
        result=partial_response(value,'AI_PROVIDER_ERROR')
        self.assertEqual(result['response_outcome']['state'],'partial')
        self.assertEqual(result['response_outcome']['reason_code'],'AI_PROVIDER_ERROR')
        self.assertEqual(result['assessment_cards'],value['assessment_cards'])
        self.assertTrue(all('signature' not in task for task in result['response_outcome']['tasks']))
        from app.chat.repositories.response_outcomes import project_outcomes
        session=SimpleNamespace(execute=lambda query:SimpleNamespace(mappings=lambda:[
            dict(id=identifier,state='completed',revision=2)]))
        projected=project_outcomes(session,str(uuid4()),[result])[0]['response_outcome']
        self.assertEqual(projected['state'],'partial')
        self.assertTrue(projected['retryable'])

    def test_submitted_questionnaire_no_longer_projects_as_pending(self):
        from app.chat.repositories.response_outcomes import project_outcomes
        message=dict(response_outcome=dict(state='awaiting_input',retryable=False,tasks=[dict(id='r',operation='present_questionnaire',state='awaiting_input')]),
            interactions=[dict(kind='questionnaire',submitted_turn_id='submitted')])
        result=project_outcomes(None,str(uuid4()),[message])[0]
        self.assertEqual(result['response_outcome']['state'],'completed')
    def test_read_receipt_is_optional_only_when_the_model_explicitly_marks_it(self):
        value = scope()
        record_receipt(value, dict(id='r',name='web_search',args={}), dict(outcome='timeout',retryable=True))
        finalize(value, FinishResponse(content='I can explain the supplied text.', tasks=[dict(id='background',required=False,receipt_ids=['r'])]))
        self.assertEqual(value['response_outcome']['state'], 'completed')
        finalize(value, FinishResponse(content='I could not verify the price.'))
        self.assertEqual(value['response_outcome']['state'], 'failed')
        self.assertTrue(value['response_outcome']['retryable'])

    def test_failure_cannot_be_hidden_by_completed_graph_decision(self):
        value = scope()
        record_receipt(value, dict(id='r',name='web_search',args={}), dict(outcome='timeout',retryable=True))
        finalize(value, FinishResponse(content='The verification failed.', outcome='completed'))
        self.assertEqual(value['response_outcome']['state'], 'failed')

    def test_committed_result_survives_a_second_failed_task(self):
        value = scope()
        record_receipt(value, dict(id='saved',name='event_manage',args={}), dict(outcome='saved'))
        record_receipt(value, dict(id='search',name='web_search',args={}), dict(outcome='timeout',retryable=True))
        finalize(value, FinishResponse(content='The event was saved; source verification failed.'))
        self.assertEqual(value['response_outcome']['state'], 'partial')

    def test_unknown_write_is_not_made_retryable_or_optional(self):
        value = scope()
        record_receipt(value, dict(id='w',name='event_manage',args={}), dict(outcome='unavailable',effect_certainty='unknown'))
        finalize(value, FinishResponse(content='The event could not be verified.', tasks=[dict(id='event',required=False,receipt_ids=['w'])]))
        self.assertEqual(value['response_outcome']['state'], 'failed')
        self.assertFalse(value['response_outcome']['retryable'])

    def test_unissued_receipt_is_rejected(self):
        from app.core.exceptions import AppError
        with self.assertRaises(AppError):
            finalize(scope(), FinishResponse(content='Saved.', tasks=[dict(id='event', receipt_ids=['invented'])]))

    def test_actual_owned_job_reference_resolves_without_a_model_repair(self):
        value=scope()
        identifier=str(uuid4())
        record_receipt(value,dict(id='native-call',name='assessment_generate',args={}),dict(outcome='queued',generation_job_id=identifier))
        finalize(value,FinishResponse(content='Practice is being prepared.',outcome='in_progress',
            tasks=[dict(id='practice',operation='assessment_generate',state='in_progress',receipt_ids=[identifier])]))
        self.assertEqual(value['response_outcome']['state'],'in_progress')

    def test_read_receipt_cannot_fulfill_a_write_operation(self):
        from app.core.exceptions import AppError
        value=scope()
        record_receipt(value,dict(id='read',name='event_lookup',args={}),dict(outcome='ok'))
        with self.assertRaises(AppError):
            finalize(value,FinishResponse(content='Saved.',tasks=[dict(id='save',operation='event_manage',receipt_ids=['read'])]))

    def test_source_required_explanation_cannot_finish_without_evidence(self):
        from app.core.exceptions import AppError
        with self.assertRaises(AppError):
            finalize(scope(),FinishResponse(content='An unsupported fact.',tasks=[dict(id='explain',grounding='study_material')]))

    def test_declared_failure_is_not_overwritten_by_queued_work(self):
        value = scope()
        record_receipt(value, dict(id='q',name='assessment_generate',args={}), dict(outcome='queued',generation_job_id=str(uuid4())))
        finalize(value, FinishResponse(content='Practice is queued; the other request is unfinished.', outcome='partial'))
        self.assertEqual(value['response_outcome']['state'], 'partial')

    def test_queued_grading_and_prepared_answers_have_distinct_states(self):
        for state, expected in [('submitted','in_progress'),('draft','awaiting_input'),('pending_transcription','awaiting_input'),('graded','completed')]:
            value = scope()
            record_receipt(value, dict(id='a',name='assessment_answer',args={}), dict(outcome=state,attempt_id=str(uuid4())))
            finalize(value, FinishResponse(content='See your assessment.'))
            self.assertEqual(value['response_outcome']['state'],expected)
            self.assertEqual(value['response_outcome']['tasks'][0]['job_kind'],'grading')

    def test_protocol_correction_supersedes_the_rejected_attempt(self):
        value = scope()
        call = dict(id='bad', name='web_search', args={})
        record_receipt(value, call, dict(outcome='rejected', code='TOOL_INVALID_ARGUMENTS'))
        record_receipt(value, dict(call,id='good',args={'query':'valid'}), dict(outcome='ok'))
        finalize(value, FinishResponse(content='Verified.'))
        self.assertEqual(value['response_outcome']['state'],'completed')

    def test_empty_failed_handoff_does_not_claim_saved_results(self):
        value = scope()
        record_receipt(value, dict(id='r',name='web_search',args={}), dict(outcome='unavailable'))
        decision = finalize(value, FinishResponse())
        self.assertEqual(value['response_outcome']['state'],'failed')
        self.assertNotIn('saved', decision.content)


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_enabled_tool_does_not_require_execution_even_for_trigger_words(self):
        for query in ('My current phone is slow.', 'Define an assessment.', 'Explain an event loop.', 'Translate: remember my notes.', 'What is a test in programming?'):
            with self.subTest(query=query):
                state = scope()
                model = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='',tool_calls=[
                    dict(id='finish',name='FinishResponse',args=dict(content='A direct contextual answer.'))])))
                service = SimpleNamespace(events=None, lookup=AsyncMock(), memory=AsyncMock(), search_summaries=AsyncMock())
                result = await tool_reply(model,[HumanMessage(content=query)],service,str(uuid4()),state,(),{})
                self.assertEqual(result.content,'A direct contextual answer.')
                self.assertEqual(model.ainvoke_messages.await_count,1)
                self.assertEqual(state['_tool_budget'].calls,0)
                service.lookup.assert_not_awaited()

    async def test_old_keyword_plan_cannot_authorize_or_require_actions(self):
        state = scope()
        state['execution_plan'] = SimpleNamespace(tool_names=['event_manage'],required_domains=['events'],required_outcome='assessment')
        selection = ToolSelection([],{},state)
        self.assertEqual(selection.selected(),[])
        model = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='A normal reply.')))
        await tool_reply(model,[HumanMessage(content='A current phone.')],None,str(uuid4()),state,(),{})
        self.assertEqual(state['response_outcome']['state'],'completed')

    async def test_questionnaire_handoff_can_finish_in_one_model_round(self):
        state = scope()
        questions = [dict(id=f'q{i}',kind='single_choice',question=f'Preference {i}?',options=[dict(id='a',label='First'),dict(id='b',label='Second')]) for i in range(5)]
        model = SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='',tool_calls=[
            dict(id='ui',name='present_questionnaire',args=dict(question='Your preferences',questions=questions)),
            dict(id='final',name='FinishResponse',args=dict(content='',outcome='awaiting_input'))])))
        await tool_reply(model,[HumanMessage(content='Ask five preferences together.')],None,str(uuid4()),state,(),{})
        self.assertEqual(model.ainvoke_messages.await_count,1)
        self.assertEqual(len(state['interactions'][0]['questions']),5)
        self.assertEqual(state['response_outcome']['state'],'awaiting_input')
        self.assertEqual(state['_tool_budget'].writes,0)


class PersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.db = PostgresSandbox()
    @classmethod
    def tearDownClass(cls): cls.db.close()

    def test_completed_graph_with_failed_task_remains_retryable_and_reruns(self):
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        from app.chat.service import ConversationService
        repository = ChatRepository(self.db.sessions)
        owner = learner_id('alice')
        request = SendTurn(conversation_id=uuid4(),client_turn_id=uuid4(),expected_revision=0,content='Verify a source.')
        calls = []
        async def scenario():
            service = ConversationService(repository)
            async def generate(*args):
                calls.append(True)
                return dict(content='Verification failed.' if len(calls)==1 else 'Verified.', response_outcome=ResponseOutcome(
                    state='failed' if len(calls)==1 else 'completed',retryable=len(calls)==1).model_dump(mode='json'))
            first = await service.send(owner,request,generate)
            self.assertEqual(first['turn']['state'],'FAILED')
            self.assertEqual(first['items'][-1]['content'],'Verification failed.')
            self.assertTrue(first['turn']['can_retry'])
            second = await service.send(owner,request.model_copy(update={'retry':True,'expected_revision':first['conversation']['revision']}),generate)
            self.assertEqual(second['turn']['state'],'SUCCEEDED',second)
            self.assertEqual(second['items'][-1]['content'],'Verified.')
            self.assertEqual(len(calls),2)
            self.assertEqual(len(second['items']),2)
            await service.close()
        asyncio.run(scenario())

    def test_legacy_false_success_projects_failure_and_allows_explicit_retry(self):
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        repository = ChatRepository(self.db.sessions)
        owner = learner_id('alice')
        request = SendTurn(conversation_id=uuid4(),client_turn_id=uuid4(),expected_revision=0,content='A source request.')
        job = repository.begin_turn(owner,request)
        repository.finish(owner,job,dict(content='Incomplete.',tool_warnings=[dict(code='REQUEST_OUTCOME_INCOMPLETE')]))
        from sqlalchemy import update
        from app.chat.repositories.tables import messages, turns
        with self.db.sessions.begin() as session:
            session.execute(update(turns).where(turns.c.id==job['turn_id']).values(response_outcome=None,orchestration_policy=None))
            session.execute(update(messages).where(messages.c.conversation_id==job['conversation_id'],messages.c.role=='assistant').values(metadata=dict(tool_warnings=[dict(code='REQUEST_OUTCOME_INCOMPLETE')])))
        page = repository.status(owner,job['conversation_id'])
        self.assertEqual(page['turn']['response_outcome']['state'],'failed')
        retry = request.model_copy(update={'retry':True,'expected_revision':page['conversation']['revision']})
        self.assertIsNone(repository.replay_turn(owner,retry))
        self.assertTrue(repository.begin_turn(owner,retry)['run'])

    def test_private_write_receipts_survive_context_checkpoint_discard(self):
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        repository=ChatRepository(self.db.sessions)
        owner=learner_id('alice')
        request=SendTurn(conversation_id=uuid4(),client_turn_id=uuid4(),expected_revision=0,content='An authorized action.')
        job=repository.begin_turn(owner,request)
        private=dict(version=1,results={'operation':{'outcome':'saved','id':'owned'}},receipts={},failed={})
        job.update(_recovery_state=private,_discard_checkpoint=True)
        repository.finish(owner,job,None,'Saved context changed. Retry with current context.')
        page=repository.status(owner,job['conversation_id'])
        self.assertNotIn('recovery_state',page['turn'])
        retry=repository.begin_turn(owner,request.model_copy(update={'retry':True,'expected_revision':page['conversation']['revision']}))
        self.assertEqual(retry['recovery_state'],private)

    def test_opted_out_memory_is_not_queued_and_opted_in_source_is_canonical(self):
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        from app.history_management.repositories.tables import capture_jobs, preferences
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert
        owner=learner_id('alice')
        repository=ChatRepository(self.db.sessions)
        with self.db.sessions.begin() as session:
            session.execute(insert(preferences).values(learner_id=owner,automatic_memory=False,revision=1).on_conflict_do_update(
                index_elements=['learner_id'],set_=dict(automatic_memory=False)))
        def finish(text):
            request=SendTurn(conversation_id=uuid4(),client_turn_id=uuid4(),expected_revision=0,content=text)
            job=repository.begin_turn(owner,request)
            repository.finish(owner,job,dict(content='A useful response.'))
            return job
        disabled=finish('I prefer examples in algebra.')
        with self.db.sessions() as session:
            self.assertIsNone(session.scalar(select(capture_jobs.c.message_id).where(capture_jobs.c.turn_id==disabled['turn_id'])))
        with self.db.sessions.begin() as session:
            session.execute(preferences.update().where(preferences.c.learner_id==owner).values(automatic_memory=True,revision=2))
        enabled=finish('I prefer shorter sessions for calculus.')
        with self.db.sessions() as session:
            capture=session.execute(select(capture_jobs).where(capture_jobs.c.turn_id==enabled['turn_id'])).mappings().one()
        source=repository.context_rows(owner,enabled['conversation_id'])[0]
        self.assertEqual(capture['message_id'],source['id'])
        self.assertEqual(capture['source_attempt'],enabled['attempt'])
        self.assertEqual(capture['preference_revision'],2)
