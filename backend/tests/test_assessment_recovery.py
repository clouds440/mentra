import os
import json
import unittest
from types import SimpleNamespace
from uuid import uuid4
from app.chat.response import ChatResponse
from app.assessments.schemas import GenerationRequest, GradedAssessment, ConceptGrade, StartAttempt, SubmitAnswers
from app.assessments.grade_alignment import align_grades
from app.langchain.generation_recovery import GenerationMismatch
from app.assessments.worker import AssessmentWorker
from tests import test_assessment_flexibility as flexible


class RecoveryContractTests(unittest.TestCase):
    def test_queued_cards_survive_chat_response_packaging_and_deduplication(self):
        queued=dict(id='job',generation_job_id='job',title='React state')
        completed=dict(id='draft',assessment=dict(id='job',questions=[]))
        response=ChatResponse(content='Building your assessment',assessment_cards=[queued,completed,dict(queued,title='Updated')])
        self.assertEqual(len(response.assessment_cards),2)
        self.assertEqual(response.assessment_cards[0]['title'],'Updated')
        self.assertEqual(response.assessment_cards[1],completed)

    def test_question_requests_above_twenty_are_capped_not_rejected(self):
        request=GenerationRequest(client_request_id=uuid4(),context_id='context',topic='React state',count=100)
        self.assertEqual(request.count,20)
        paper=GenerationRequest(client_request_id=uuid4(),context_id='context',topic='React',count=100,question_format='mock_paper',
            total_marks=100,paper_sections=[dict(title='Main',question_count=100,part_marks=[1])])
        self.assertEqual(paper.paper_sections[0].question_count,20)
        self.assertEqual(paper.total_marks,20)

    def test_grading_concept_keys_and_scales_are_bound_by_server(self):
        question=dict(id='question',marks=2,concept_ids=['canonical'])
        result=GradedAssessment(questions=[dict(question_id='question',score=1,confidence=.95,feedback='Partly correct',
            concept_grades={'invented':dict(score=5,max_score=10,confidence=.95)})])
        align_grades(result,[question])
        self.assertEqual(set(result.questions[0].concept_grades),{'canonical'})
        self.assertEqual(result.questions[0].concept_grades['canonical'].max_score,2)
        self.assertEqual(result.questions[0].concept_grades['canonical'].score,1)

    def test_missing_multi_concept_attribution_stays_low_confidence(self):
        result=GradedAssessment(questions=[dict(question_id='q',score=2,confidence=.95,feedback='Correct')])
        align_grades(result,[dict(id='q',marks=2,concept_ids=['one','two'])])
        self.assertTrue(all(detail.confidence<.5 for detail in result.questions[0].concept_grades.values()))

    def test_unknown_question_ids_are_still_rejected(self):
        result=GradedAssessment(questions=[dict(question_id='other',score=1,confidence=.9,feedback='Correct')])
        with self.assertRaises(GenerationMismatch): align_grades(result,[dict(id='q',marks=2,concept_ids=['c'])])


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Requires isolated PostgreSQL')
class RecoveryEngineTests(unittest.IsolatedAsyncioTestCase):
    setUp=flexible.FlexibleEngineTests.setUp
    request=flexible.FlexibleEngineTests.request

    async def test_twenty_question_generation_uses_four_content_calls(self):
        import asyncio
        original=self.factory.with_structured_output
        offsets=[]; active=[0]; peak=[0]
        def capture(schema,**kwargs):
            model=original(schema,**kwargs)
            if schema.__name__ not in ('GeneratedAssessment', 'GeneratedAssessmentBatch'): return model
            async def invoke(messages):
                offsets.append(json.loads(messages[-1].content)['question_offset'])
                active[0]+=1; peak[0]=max(peak[0],active[0])
                try:
                    await asyncio.sleep(.02)
                    return await model.ainvoke(messages)
                finally: active[0]-=1
            return SimpleNamespace(ainvoke=invoke)
        self.factory.with_structured_output=capture
        value=await self.service.generate(self.owner,self.request(count=100,question_format='written'))
        self.assertEqual(len(value.questions),20)
        self.assertEqual(offsets,[0,6,12,18])
        self.assertEqual(peak[0],2)

    async def test_regular_quiz_generates_in_a_single_content_call(self):
        original=self.factory.with_structured_output; calls=[]
        def capture(schema,**kwargs):
            model=original(schema,**kwargs)
            if schema.__name__ not in ('GeneratedAssessment', 'GeneratedAssessmentBatch'): return model
            async def invoke(messages):
                calls.append(json.loads(messages[-1].content)['count'])
                return await model.ainvoke(messages)
            return SimpleNamespace(ainvoke=invoke)
        self.factory.with_structured_output=capture
        value=await self.service.generate(self.owner,self.request(count=10,question_format='mcq'))
        self.assertEqual(len(value.questions),10)
        self.assertEqual(calls,[10])

    async def test_model_concept_mismatch_no_longer_breaks_evaluation(self):
        value=await self.service.generate(self.owner,self.request(count=6,question_format='written'))
        attempt=self.service.repository.start(self.owner,str(value.id),StartAttempt(client_request_id=uuid4()))
        answers={str(q.id):'My explanation' for q in value.questions}
        self.service.submit(self.owner,str(attempt.id),SubmitAnswers(client_request_id=uuid4(),expected_revision=1,answers=answers))
        original=self.factory.with_structured_output
        def drift(schema,**kwargs):
            model=original(schema,**kwargs)
            if schema.__name__!='GradedAssessment': return model
            async def invoke(messages):
                result=await model.ainvoke(messages)
                for grade in result.questions:
                    grade.concept_grades={'wrong-id':ConceptGrade(score=5,max_score=10,confidence=.95)}
                return result
            return SimpleNamespace(ainvoke=invoke)
        self.factory.with_structured_output=drift
        await AssessmentWorker(self.service).run_once()
        graded=self.service.repository.attempt(self.owner,str(attempt.id))
        self.assertEqual(graded.state,'graded')
        self.assertEqual(graded.answers,answers)
        self.assertEqual(graded.id,attempt.id)
