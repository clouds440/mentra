import os
import unittest
from uuid import uuid4
from io import BytesIO
from unittest.mock import AsyncMock, patch
from sqlalchemy import update
from app.chat.schemas import SendTurn
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.tables import conversations
from app.chat.attachments import AttachmentService
from app.chat.repositories.attachments import AttachmentRepository
from app.history_management.budgets import ToolBudget
from app.langchain.workflow_tools import create_workflow_tools
from app.assessments.schemas import SubmitAnswers
from app.assessments.worker import AssessmentWorker
from app.core.exceptions import AppError
from tests import test_assessments as fixtures


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated database')
class ChatAssessmentTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.AssessmentTests.setUp
    # Reuse setup only, rather than re-running the inherited assessment cases.
    def conversation(self, owner=None):
        identifier = str(uuid4())
        ChatRepository(self.db.sessions).begin_turn(owner or self.owner, SendTurn(conversation_id=identifier,
            client_turn_id=uuid4(), expected_revision=0, content='Generate a quiz'))
        return identifier

    async def draft(self):
        conversation = self.conversation()
        card = await self.service.generate_chat(self.owner, conversation, self.request)
        return conversation, card

    def answer_tool(self, conversation, text='', attachment_ids=()):
        scope = dict(assessment_service=self.service, conversation_id=conversation,
            current_user_message_id=str(uuid4()), current_answer_text=text,
            attachment_service=AttachmentService(AttachmentRepository(self.db.sessions)),
            assessment_attachment_ids=list(attachment_ids))
        tool = next(t for t in create_workflow_tools(self.owner, scope, ToolBudget()) if t.name=='assessment_answer')
        return tool, scope

    async def test_draft_publish_replay_and_survival_after_chat_deletion(self):
        conversation, card = await self.draft()
        self.assertIsNone(card['assessment_id'])
        self.assertEqual(self.service.repository.list(self.owner)['items'], [])
        self.assertNotIn('model_answer', str(card)); self.assertNotIn('rubric', str(card))
        replay = await self.service.generate_chat(self.owner, conversation, self.request)
        self.assertEqual(card['id'], replay['id'])
        saved = self.service.chat.publish(self.owner, card['id'])
        self.assertEqual(saved['assessment_id'], self.service.chat.publish(self.owner, card['id'])['assessment_id'])
        self.assertEqual(card['assessment']['questions'], saved['assessment']['questions'])
        with self.assertRaises(AppError): self.service.chat.publish(self.other, card['id'])
        with self.db.sessions.begin() as session:
            session.execute(update(conversations).where(conversations.c.id==conversation).values(deleted_at=self.service.repository.clock()))
        with self.assertRaises(AppError): self.service.chat.detail(self.owner, card['id'])
        self.assertEqual(str(self.service.repository.detail(self.owner,saved['assessment_id']).id),saved['assessment_id'])

    async def test_auto_add_is_opt_in_and_revision_fenced(self):
        self.assertFalse(self.service.chat.settings(self.owner)['auto_add'])
        self.service.chat.update_settings(self.owner,True,0)
        with self.assertRaises(AppError): self.service.chat.update_settings(self.owner,False,0)
        _,card = await self.draft()
        self.assertIsNotNone(card['assessment_id'])
        self.assertEqual(len(self.service.repository.list(self.owner)['items']),1)

    async def test_typed_answers_review_then_grade_with_exact_provenance(self):
        conversation,card = await self.draft()
        tool,scope = self.answer_tool(conversation,'Here are portions of my work:\n1. First answer\n2. Second answer')
        result = await tool.ainvoke(dict(draft_id=card['id'],answers={'1':'First answer','2':'Second answer'}))
        attempt = self.service.repository.attempt(self.owner,result['attempt_id'])
        self.assertEqual(attempt.state,'pending_transcription')
        self.assertIsNotNone(scope['assessment_cards'][0]['assessment_id'])
        body = SubmitAnswers(expected_revision=attempt.revision,client_request_id=uuid4(),answers=attempt.extraction['answers'])
        with self.assertRaises(AppError): self.service.submit(self.owner,str(attempt.id),body)
        self.service.submit(self.owner,str(attempt.id),body.model_copy(update={'transcription_confirmed':True}))
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).state,'graded')
        tool,_ = self.answer_tool(conversation,'Actual student answer')
        with self.assertRaises(AppError): await tool.ainvoke(dict(draft_id=card['id'],answers={'1':'Invented answer'}))

    async def test_chat_document_upload_and_foreign_file_rejection(self):
        conversation,card = await self.draft()
        attachments = AttachmentRepository(self.db.sessions)
        file = attachments.create(self.owner,'answers.txt',b'1. First answer\n2. Second answer')
        with self.db.sessions.begin() as session: attachments.bind(session,self.owner,[file['id']],conversation)
        tool,_ = self.answer_tool(conversation,attachment_ids=[file['id']])
        result = await tool.ainvoke(dict(draft_id=card['id'],attachment_id=file['id']))
        attempt = self.service.repository.attempt(self.owner,result['attempt_id'])
        self.assertEqual(attempt.extraction['answers'], {q['id']:text for q,text in zip(card['assessment']['questions'],['First answer','Second answer'])})
        tool,_ = self.answer_tool(conversation)
        with self.assertRaises(AppError): await tool.ainvoke(dict(draft_id=card['id'],attachment_id=file['id']))

    async def test_saved_assessment_can_be_answered_from_another_chat(self):
        _,card = await self.draft()
        saved = self.service.chat.publish(self.owner,card['id'])
        tool,scope = self.answer_tool(self.conversation(),'First answer and Second answer')
        result = await tool.ainvoke(dict(assessment_id=saved['assessment_id'],answers={'1':'First answer','2':'Second answer'}))
        self.assertEqual(result['outcome'],'pending_transcription')
        self.assertIsNone(scope['assessment_cards'][0]['id'])

    async def test_handwritten_chat_image_uses_vision_and_requires_review(self):
        conversation,card = await self.draft()
        attachments = AttachmentRepository(self.db.sessions)
        file = attachments.create(self.owner,'handwritten.png',b'\x89PNG\r\n\x1a\nimage-fixture')
        with self.db.sessions.begin() as session: attachments.bind(session,self.owner,[file['id']],conversation)
        extraction = dict(answers={q['id']:f'Written answer {i}' for i,q in enumerate(card['assessment']['questions'],1)},
            warnings=[], requires_confirmation=True, handwriting_support='vision_requires_review')
        tool,_ = self.answer_tool(conversation,attachment_ids=[file['id']])
        with patch('app.vision.assessment_extractor.AssessmentAnswerExtractor.extract',new=AsyncMock(return_value=extraction)) as vision:
            with patch.object(self.service.reader,'read',side_effect=AssertionError('OCR must not run before successful vision')):
                result = await tool.ainvoke(dict(draft_id=card['id'],attachment_id=file['id']))
            vision.assert_awaited_once()
        attempt = self.service.repository.attempt(self.owner,result['attempt_id'])
        self.assertEqual(attempt.extraction['handwriting_support'],'vision_requires_review')
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(),answers=extraction['answers'],transcription_confirmed=True))
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        self.assertEqual(self.service.repository.attempt(self.owner,str(attempt.id)).state,'graded')

    async def test_complete_numbered_answers_queue_grading_without_extra_review(self):
        conversation,card = await self.draft()
        tool,_ = self.answer_tool(conversation,'Evaluate these answers:\n1. First answer\n2. Second answer')
        result = await tool.ainvoke(dict(draft_id=card['id'],answers={'1':'First answer','2':'Second answer'}))
        self.assertEqual(result['outcome'],'submitted')
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        self.assertEqual(self.service.repository.attempt(self.owner,result['attempt_id']).state,'graded')

    async def test_partial_answers_continue_across_messages_and_replay_without_overwriting(self):
        conversation,card = await self.draft()
        first,first_scope = self.answer_tool(conversation,'1. First answer')
        one = await first.ainvoke(dict(draft_id=card['id'],answers={'1':'First answer'}))
        second,_ = self.answer_tool(conversation,'2. Second answer')
        two = await second.ainvoke(dict(draft_id=card['id'],answers={'2':'Second answer'}))
        self.assertEqual(one['attempt_id'],two['attempt_id'])
        attempt = self.service.repository.attempt(self.owner,two['attempt_id'])
        self.assertEqual(len(attempt.extraction['answers']),2)
        replay_tool = next(t for t in create_workflow_tools(self.owner,first_scope,ToolBudget()) if t.name=='assessment_answer')
        await replay_tool.ainvoke(dict(draft_id=card['id'],answers={'1':'First answer'}))
        self.assertEqual(self.service.repository.attempt(self.owner,two['attempt_id']).revision,attempt.revision)
        first_scope['current_answer_text']='A changed answer'
        conflict_tool = next(t for t in create_workflow_tools(self.owner,first_scope,ToolBudget()) if t.name=='assessment_answer')
        with self.assertRaises(AppError) as error:
            await conflict_tool.ainvoke(dict(draft_id=card['id'],answers={'1':'A changed answer'}))
        self.assertEqual(error.exception.code,'OPERATION_CONFLICT')
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(expected_revision=attempt.revision,
            client_request_id=uuid4(),answers=attempt.extraction['answers'],transcription_confirmed=True))
        await AssessmentWorker(self.service).run_once()
        self.assertEqual(len(self.service.repository.attempts(self.owner,card['assessment']['id'])),1)

    async def test_direct_submission_retry_rejects_changed_answers(self):
        conversation,card = await self.draft()
        tool,scope = self.answer_tool(conversation,'Evaluate:\n1. First answer\n2. Second answer')
        result = await tool.ainvoke(dict(draft_id=card['id'],answers={'1':'First answer','2':'Second answer'}))
        scope['current_answer_text']='Evaluate:\n1. Changed answer\n2. Second answer'
        retry = next(t for t in create_workflow_tools(self.owner,scope,ToolBudget()) if t.name=='assessment_answer')
        with self.assertRaises(AppError) as error:
            await retry.ainvoke(dict(draft_id=card['id'],answers={'1':'Changed answer','2':'Second answer'}))
        self.assertEqual(error.exception.code,'OPERATION_CONFLICT')
        self.assertEqual(self.service.repository.attempt(self.owner,result['attempt_id']).state,'submitted')

    async def test_failed_upload_retains_saved_card_and_retryable_attempt(self):
        conversation,card = await self.draft()
        attachments = AttachmentRepository(self.db.sessions)
        file = attachments.create(self.owner,'answers.txt',b'1. First answer')
        with self.db.sessions.begin() as session: attachments.bind(session,self.owner,[file['id']],conversation)
        tool,scope = self.answer_tool(conversation,attachment_ids=[file['id']])
        with patch.object(self.service,'upload_paper_with_vision',new=AsyncMock(side_effect=RuntimeError('provider failure'))):
            result = await tool.ainvoke(dict(draft_id=card['id'],attachment_id=file['id']))
        self.assertEqual(result['outcome'],'answer_preparation_failed')
        self.assertTrue(result['assessment_saved'])
        self.assertEqual(scope['assessment_cards'][0]['attempt_id'],result['attempt_id'])
        self.assertEqual(self.service.repository.attempt(self.owner,result['attempt_id']).state,'draft')

    async def test_status_returns_grade_feedback_and_recoverable_card(self):
        conversation,card = await self.draft()
        tool,_ = self.answer_tool(conversation,'Evaluate:\n1. First answer\n2. Second answer')
        result = await tool.ainvoke(dict(draft_id=card['id'],answers={'1':'First answer','2':'Second answer'}))
        await AssessmentWorker(self.service).run_once()
        scope = dict(assessment_service=self.service,conversation_id=conversation)
        status = next(t for t in create_workflow_tools(self.owner,scope,ToolBudget()) if t.name=='assessment_status')
        packet = await status.ainvoke(dict(assessment_id=card['assessment']['id']))
        self.assertTrue(packet['attempts'][0]['feedback'])
        self.assertEqual(scope['assessment_cards'][0]['attempt_id'],result['attempt_id'])
        self.assertNotIn('model_answer',str(packet))

    async def test_followup_and_revision_preserve_original_without_starting_attempts(self):
        conversation,card = await self.draft()
        saved = self.service.chat.publish(self.owner,card['id'])
        scope = dict(assessment_service=self.service,conversation_id=conversation,
            current_user_message_id=str(uuid4()),current_answer_text='Make it easier and use three questions')
        tools = {t.name:t for t in create_workflow_tools(self.owner,scope,ToolBudget())}
        question = await tools['assessment_question'].ainvoke(dict(draft_id=card['id'],number=1))
        self.assertEqual(question['prompt'],card['assessment']['questions'][0]['prompt'])
        self.assertEqual(self.service.repository.attempts(self.owner,saved['assessment_id']),[])
        result = await tools['assessment_revise'].ainvoke(dict(draft_id=card['id'],instructions=scope['current_answer_text'],count=3))
        revised = scope['assessment_cards'][0]
        self.assertNotEqual(revised['id'],card['id'])
        self.assertEqual(len(revised['assessment']['questions']),3)
        self.assertIsNone(revised['assessment_id'])
        self.assertEqual(self.service.chat.detail(self.owner,card['id'])['assessment'],card['assessment'])
        self.assertEqual(self.service.repository.attempts(self.owner,saved['assessment_id']),[])
        retry_tools = {t.name:t for t in create_workflow_tools(self.owner,scope,ToolBudget())}
        replay = await retry_tools['assessment_revise'].ainvoke(dict(draft_id=card['id'],instructions=scope['current_answer_text'],count=3))
        self.assertEqual(result['draft_id'],replay['draft_id'])
        with self.assertRaises(AppError):
            await retry_tools['assessment_question'].ainvoke(dict(draft_id=card['id'],number=10))

    async def test_revision_rejects_foreign_chat_and_invented_instructions(self):
        conversation,card = await self.draft()
        scope = dict(assessment_service=self.service,conversation_id=self.conversation(),
            current_user_message_id=str(uuid4()),current_answer_text='Make it easier')
        tool = next(t for t in create_workflow_tools(self.owner,scope,ToolBudget()) if t.name=='assessment_revise')
        with self.assertRaises(AppError): await tool.ainvoke(dict(draft_id=card['id'],instructions='Make it easier'))
        scope['conversation_id']=conversation
        tool = next(t for t in create_workflow_tools(self.owner,scope,ToolBudget()) if t.name=='assessment_revise')
        with self.assertRaises(AppError): await tool.ainvoke(dict(draft_id=card['id'],instructions='Invented request'))

    async def test_deleted_saved_card_cannot_recreate_the_assessment(self):
        _,card = await self.draft()
        saved = self.service.chat.publish(self.owner,card['id'])
        self.service.repository.remove(self.owner,saved['assessment_id'])
        self.assertTrue(self.service.chat.detail(self.owner,card['id'])['deleted'])
        with self.assertRaises(AppError): self.service.chat.publish(self.owner,card['id'])
        self.assertEqual(self.service.repository.list(self.owner)['items'],[])

    async def test_student_can_explicitly_start_over_instead_of_merging_partial_work(self):
        conversation,card = await self.draft()
        first,_ = self.answer_tool(conversation,'First answer')
        one = await first.ainvoke(dict(draft_id=card['id'],answers={'1':'First answer'}))
        fresh,_ = self.answer_tool(conversation,'Start over: New answer')
        two = await fresh.ainvoke(dict(draft_id=card['id'],answers={'1':'New answer'},new_attempt=True))
        self.assertNotEqual(one['attempt_id'],two['attempt_id'])
        old = self.service.repository.attempt(self.owner,one['attempt_id'])
        self.assertEqual(list(old.extraction['answers'].values()),['First answer'])

    async def test_large_revision_sends_full_questions_only_for_current_batch(self):
        conversation = self.conversation()
        invoke = self.service.workflows.llm.ainvoke
        async def long_questions(source,payload,**kwargs):
            generated = await invoke(source,payload,**kwargs)
            for question in generated.questions: question.prompt += ' supporting detail' * 120
            return generated
        request = self.request.model_copy(update={'count':10})
        with patch.object(self.service.workflows.llm,'ainvoke',side_effect=long_questions):
            card = await self.service.generate_chat(self.owner,conversation,request)
        payloads = []
        async def capture(source,payload,**kwargs):
            payloads.append(payload)
            return await invoke(source,payload,**kwargs)
        scope = dict(assessment_service=self.service,conversation_id=conversation,
            current_user_message_id=str(uuid4()),current_answer_text='Make the assessment easier')
        tool = next(t for t in create_workflow_tools(self.owner,scope,ToolBudget()) if t.name=='assessment_revise')
        with patch.object(self.service.workflows.llm,'ainvoke',side_effect=capture):
            await tool.ainvoke(dict(draft_id=card['id'],instructions=scope['current_answer_text']))
        self.assertEqual([len(payload['original_questions']) for payload in payloads],[3,3,3,1])
        self.assertTrue(all(len(payload['original_overview'])==10 for payload in payloads))
        self.assertTrue(all(payload['original_overview'][0]['truncated'] for payload in payloads))
        self.assertNotIn('model_answer',str(payloads))
