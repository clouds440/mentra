import unittest
from uuid import uuid4
from app.assessments.schemas import GenerationRequest, StartAttempt, SubmitAnswers, SaveDraftAnswers, GeneratedQuestion
from app.assessments.worker import AssessmentWorker
from app.core.exceptions import AppError
from pydantic import ValidationError
from tests import test_assessments as fixtures

class MCQAssessmentTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.AssessmentTests.setUp
    async def test_generation_partial_persistence_submission_results_and_evidence(self):
        request=self.request.model_copy(update={'question_format':'mcq','count':5})
        assessment=await self.service.generate(self.owner,request)
        self.assertEqual(len(assessment.questions),5)
        self.assertNotIn('correct_option_id',assessment.model_dump_json())
        self.assertTrue(all(len(q.options)==2 for q in assessment.questions))
        attempt=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        answers={str(assessment.questions[0].id):'a'}
        body=SaveDraftAnswers(expected_revision=attempt.revision,answers=answers)
        saved=self.service.repository.save_draft_answers(self.owner,str(attempt.id),body)
        self.assertEqual(saved.answers,answers)
        self.assertEqual(self.service.repository.save_draft_answers(self.owner,str(attempt.id),body).revision,saved.revision)
        with self.assertRaises(AppError): self.service.repository.save_draft_answers(self.other,str(attempt.id),body)
        with self.assertRaises(AppError): self.service.repository.save_draft_answers(self.owner,str(attempt.id),body.model_copy(update={'answers':{str(assessment.questions[1].id):'b'}}))
        invalid=SubmitAnswers(expected_revision=saved.revision,client_request_id=uuid4(),answers={str(q.id):'forged' for q in assessment.questions})
        with self.assertRaises(AppError): self.service.submit(self.owner,str(attempt.id),invalid)
        submit=invalid.model_copy(update={'answers':{str(q.id):'a' if i<3 else 'b' for i,q in enumerate(assessment.questions)},'assistance':'independent'})
        self.service.submit(self.owner,str(attempt.id),submit)
        self.assertTrue(await AssessmentWorker(self.service).run_once())
        result=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(result.state,'graded');self.assertEqual(result.evidence_status,'applied')
        self.assertEqual(sum(q.score for q in result.grades),6)
        by_id = {grade.question_id: grade for grade in result.grades}
        for index, question in enumerate(assessment.questions):
            grade = by_id[str(question.id)]
            self.assertEqual(grade.outcome, 'correct' if index < 3 else 'wrong')
            self.assertEqual(grade.correct_answer, question.options[0].label)
        from app.langchain.workflow_tools import create_workflow_tools
        from app.history_management.budgets import ToolBudget
        tools = {tool.name: tool for tool in create_workflow_tools(self.owner,
            dict(assessment_service=self.service, conversation_id=str(uuid4())), ToolBudget())}
        status = await tools['assessment_status'].ainvoke(dict(assessment_id=str(assessment.id)))
        results = status['attempts'][0]['results']
        self.assertEqual(len(results), 5)
        self.assertEqual({value['question_id']: value['outcome'] for value in results},
                         {identifier: grade.outcome for identifier, grade in by_id.items()})
        self.assertEqual(self.service.submit(self.owner,str(attempt.id),submit).state,'graded')
        with self.assertRaises(AppError): self.service.repository.save_draft_answers(self.owner,str(attempt.id),body)
    def test_private_correct_option_validation_and_legacy_fingerprint(self):
        self.assertNotIn('question_format',self.request.fingerprint_payload())
        args=dict(prompt='Question?',concept_ids=['c'],difficulty=.5,marks=1,model_answer='A',rubric='A',options=[dict(id='a',label='A'),dict(id='b',label='B')],correct_option_id='x')
        with self.assertRaises(ValidationError): GeneratedQuestion(**args)

    async def test_llm_tool_format_defaults_and_question_discussion(self):
        from app.langchain.workflow_tools import create_workflow_tools, GeneratePractice
        from app.chat.repositories.postgres import ChatRepository
        from app.chat.schemas import SendTurn
        from app.history_management.budgets import ToolBudget
        self.assertEqual(GeneratePractice(context_id=self.request.context_id,topic='Equations').question_format,'written')
        await self.service.generate(self.owner,self.request)
        cid=str(uuid4())
        ChatRepository(self.db.sessions).begin_turn(self.owner,SendTurn(conversation_id=cid,client_turn_id=uuid4(),expected_revision=0,content='Interactive quiz'))
        scope=dict(assessment_service=self.service,conversation_id=cid,current_user_message_id=str(uuid4()))
        tools={t.name:t for t in create_workflow_tools(self.owner,scope,ToolBudget())}
        result=await tools['assessment_generate'].ainvoke(dict(context_id=self.request.context_id,topic='Equations',count=5,question_format='mcq'))
        card=scope['assessment_cards'][0]
        self.assertEqual(len(card['assessment']['questions']),5)
        question=await tools['assessment_question'].ainvoke(dict(draft_id=result['draft_id'],number=1))
        self.assertEqual(len(question['options']),2)
        self.assertNotIn('correct_option_id',str(question))
        self.assertNotIn('model_answer',str(question))
        self.assertIsNotNone(card['assessment_id'])
        self.assertEqual(str(self.service.repository.detail(self.owner,card['assessment_id']).id),card['assessment_id'])
        replay_tools={t.name:t for t in create_workflow_tools(self.owner,scope,ToolBudget())}
        replay=await replay_tools['assessment_generate'].ainvoke(dict(context_id=self.request.context_id,topic='Equations',count=5,question_format='mcq'))
        self.assertEqual(replay['assessment_id'],card['assessment_id'])

    async def test_same_mcq_accepts_interactive_typed_and_reviewed_ocr_answers(self):
        from io import BytesIO
        from app.documents.schemas import DocumentContent
        assessment=await self.service.generate(self.owner,self.request.model_copy(update={'question_format':'mcq'}))
        ids=[str(q.id) for q in assessment.questions]
        class Reader:
            def read(self,*args,**kwargs):
                return DocumentContent(format='text',media_type='text/plain',blocks=[dict(text='1. A\n2. B',page=1,method='OCR')],warnings=['Review OCR'],reader_revision='test-ocr')
        self.service.reader=Reader()
        for mode in ('interactive','typed','ocr'):
            attempt=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
            answers={ids[0]:'a',ids[1]:'b'} if mode=='interactive' else {ids[0]:'A supported explanation.',ids[1]:' B) '}
            if mode=='ocr':
                attempt=self.service.upload_paper(self.owner,str(attempt.id),attempt.revision,BytesIO(b'paper'),'answers.txt')
                answers=attempt.extraction['answers']
            body=SubmitAnswers(expected_revision=attempt.revision,client_request_id=uuid4(),answers=answers,transcription_confirmed=mode=='ocr')
            if mode=='ocr':
                with self.assertRaises(AppError): self.service.submit(self.owner,str(attempt.id),body.model_copy(update={'transcription_confirmed':False}))
            submitted=self.service.submit(self.owner,str(attempt.id),body)
            self.assertEqual(submitted.answers,{ids[0]:'a',ids[1]:'b'})
            self.assertTrue(await AssessmentWorker(self.service).run_once())
            graded=self.service.repository.attempt(self.owner,str(attempt.id))
            self.assertEqual(graded.state,'graded'); self.assertEqual(graded.evidence_status,'applied')
            self.assertEqual(sum(q.score for q in graded.grades),2)
            self.assertEqual(self.service.submit(self.owner,str(attempt.id),body).state,'graded')

    async def test_provider_cannot_change_the_selected_assessment_format(self):
        from unittest.mock import patch
        invoke=self.service.workflows.llm.ainvoke
        async def wrong_format(source,payload,**kwargs):
            return await invoke(source,dict(payload,question_format='mcq'),**kwargs)
        with patch.object(self.service.workflows.llm,'ainvoke',side_effect=wrong_format):
            with self.assertRaises(AppError) as caught: await self.service.generate(self.owner,self.request)
        self.assertEqual(caught.exception.code,'ASSESSMENT_INVALID_GENERATION')
        self.assertEqual(self.service.repository.list(self.owner)['items'],[])
