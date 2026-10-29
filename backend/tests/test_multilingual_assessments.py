"""Native scripts are content; protocol option IDs and ownership stay stable."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from sqlalchemy import select,func
from app.assessments.schemas import GeneratedAssessment,GenerationRequest,StartAttempt,SubmitAnswers
from app.assessments.service import create_assessments
from app.assessments.worker import AssessmentWorker
from app.langchain.generation_recovery import validate_questions,invoke_generated,GenerationMismatch
from app.langchain.prompts import PromptSource
from app.langchain.llm import MentraLLM
from app.langchain.concept_identity import ConceptIdentityResolver
from app.learner.engine import LearnerEngine
from app.learner.schemas import ResolveLearningContextRequest,GeneratedConceptsRequest
from app.learner.repositories.tables.evidence import learning_evidence
from testing.history_model import HistoryChatFactory
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


def question(labels=('صحيح','خطأ'),options=True):
    return GeneratedAssessment(title='اختبار',questions=[dict(prompt='حرف الباء له نقطة واحدة أسفله.',
        difficulty=.2,marks=1,concept_names=['تمييز الحروف'],model_answer='صحيح',rubric='تحديد العبارة الصحيحة',
        options=[dict(id='true',label=labels[0]),dict(id='false',label=labels[1])] if options else [],
        correct_option_id='true' if options else None)])


class FormatTests(unittest.IsolatedAsyncioTestCase):
    def test_display_language_never_changes_boolean_protocol(self):
        # Fixtures exercise different scripts; production has no language allowlist.
        for labels in [('صحيح','خطأ'),('درست','غلط'),('正しい','誤り'),('Vrai','Faux')]:
            with self.subTest(labels=labels):
                validate_questions(question(labels),count=1,question_format='true_false',
                    concepts=None,tokens=set(),grounded=False,previous=[])
        invalid=question();invalid.questions[0].options[0].id='invented'
        with self.assertRaises(GenerationMismatch):
            validate_questions(invalid,count=1,question_format='true_false',concepts=None,tokens=set(),grounded=False,previous=[])

    async def test_mixed_format_repair_identifies_the_actual_broken_item(self):
        plan=[dict(question_type='true_false',answer_mode='single_choice',marks=1)]
        llm=SimpleNamespace(ainvoke=AsyncMock(side_effect=[question(options=False),question()]))
        await invoke_generated(llm,PromptSource.ASSESSMENT_GENERATION,{},output_schema=GeneratedAssessment,
            validate=lambda result:validate_questions(result,count=1,question_format='mixed',plan=plan,
                concepts=None,tokens=set(),grounded=False,previous=[]))
        feedback=llm.ainvoke.call_args_list[1].args[1]['repair_feedback']
        self.assertEqual(feedback['question_index'],1)
        self.assertEqual(feedback['expected_answer_mode'],'single_choice')
        self.assertEqual(feedback['actual_option_count'],0)
        self.assertNotIn('حرف',str(feedback))


class NativeLearnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_skills_reuse_grouped_identity_and_remain_gradeable(self):
        db=PostgresSandbox();self.addCleanup(db.close)
        owner=learner_id('alice');llm=MentraLLM(HistoryChatFactory())
        learner=LearnerEngine(db.repository,generated_concept_resolver=ConceptIdentityResolver(llm))
        for topic,label in [('الحروف العربية','تمييز الباء والتاء'),('日本語の文字','ひらがなを読む')]:
            context=learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=owner,name=topic))
            req=GeneratedConceptsRequest(learner_id=owner,context_id=context.context_id,topic=topic,labels=[label],permissive=True)
            first=await learner.resolve_generated_concepts(req)
            again=await learner.resolve_generated_concepts(req)
            self.assertEqual([x.id for x in first],[x.id for x in again])
            self.assertEqual(learner.get_skill_topics(owner,[first[0].id])[first[0].id]['label'],label)
            service=create_assessments(db.sessions,llm,learner)
            assessment=await service.generate(owner,GenerationRequest(client_request_id=uuid4(),context_id=context.context_id,
                topic=topic,concept_names=[label],count=1,question_format='true_false'))
            with db.sessions() as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),0)
            attempt=service.repository.start(owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
            service.submit(owner,str(attempt.id),SubmitAnswers(expected_revision=attempt.revision,
                client_request_id=uuid4(),answers={str(assessment.questions[0].id):'true'}))
            await AssessmentWorker(service).run_once()
            self.assertEqual(service.repository.attempt(owner,str(attempt.id)).state,'graded')
