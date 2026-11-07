import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from app.assessments.schemas import GeneratedAssessmentBatch
from app.assessments.quality import stored_question
from app.langchain.choice_review import ChoiceReviewer,ChoiceReviewBatch,IndependentSolutionBatch
from app.langchain.generation_recovery import GenerationMismatch,invoke_generated,validate_questions
from app.langchain.prompts import PromptSource
from tests.test_structured_assessment_repair import item


def verdict(position=1,**changes):
    return dict(dict(position=position,answer_ids=['a'],answerable=True,explanation_valid=True,
        scope_preserved=True,requested_change_met=True,change_kind='reasoning_steps',change_basis='Adds a comparison step.',confidence=1,reason_code='ok'),**changes)


class ChoiceReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_review_uses_local_positions_and_restores_server_positions(self):
        llm=SimpleNamespace(ainvoke=AsyncMock(return_value=ChoiceReviewBatch(items=[verdict()])))
        result=await ChoiceReviewer(llm)._call(dict(questions=[dict(position=3,prompt='Task',independent_solution=dict(position=3))]),ChoiceReviewBatch)
        sent=llm.ainvoke.call_args.args[1]['questions'][0]
        self.assertEqual(sent['position'],1);self.assertEqual(sent['independent_solution']['position'],1)
        self.assertEqual(result.items[0].position,3)
    def test_selectable_letter_list_cannot_keep_an_unavailable_seventh_answer(self):
        from app.assessments.quality import check_question
        from app.assessments.schemas import GeneratedQuestion
        q=GeneratedQuestion(prompt='Select all non-joining letters.\n\nا ب د س ر م و',question_type='multiple_select',
            answer_mode='multiple_choice',marks=1,difficulty=.3,options=[dict(id=str(i),label=c) for i,c in enumerate('ابدسرم')],
            correct_option_ids=['0','2','4'],model_answer='ا د ر',rubric='One mark for the exact selection.')
        with self.assertRaises(GenerationMismatch):check_question(q)
        q.prompt='Select all non-joining letters.\n\nا ب د س ر م'
        check_question(q)
    def test_official_provider_review_uses_schema_prompted_json_not_named_tool_calls(self):
        from app.langchain.llm import MentraLLM
        from app.langchain.model_factory import ModelFactory
        from tests.test_model_factory import configured_settings
        from unittest.mock import Mock,patch
        factory=ModelFactory(configured_settings(ai_base_url='https://api.deepseek.com'))
        model=SimpleNamespace(with_structured_output=Mock())
        with patch.object(factory,'get_model',return_value=model):
            MentraLLM(factory)._model(PromptSource.ASSESSMENT_CHOICE_REVIEW,IndependentSolutionBatch)
        self.assertEqual(model.with_structured_output.call_args.kwargs['method'],'json_mode')

    def test_unicode_word_facts_do_not_invent_letters_or_block_preceding_alif_join(self):
        from app.langchain.assessment_reference import word_facts
        rows={row['text']:row for row in word_facts('بَاب دَرْس بَيْت مَدْرَسَة')}
        self.assertEqual(rows['باب']['adjacent_joins'],[True,False])
        self.assertEqual(rows['درس']['adjacent_joins'],[False,False])
        self.assertEqual(rows['بيت']['adjacent_joins'],[True,True])
        self.assertEqual(rows['مدرسة']['letters'],list('مدرسة'))
        self.assertEqual(rows['مدرسة']['adjacent_joins'],[True,False,False,True])
        self.assertEqual(word_facts('ب\u200cاب'),[])
        variants=word_facts('كُتُب كُتُبُ')
        self.assertEqual(len(variants),2)
        self.assertEqual(variants[0]['marks'][-1]['marks'],[])
        self.assertEqual(variants[1]['marks'][-1]['marks'],['ARABIC DAMMA'])

    async def test_reviewer_does_not_receive_the_proposed_key_and_caches_only_identical_checked_content(self):
        llm=SimpleNamespace(ainvoke=AsyncMock(return_value=ChoiceReviewBatch(items=[verdict()])))
        reviewer=ChoiceReviewer(llm);question=GeneratedAssessmentBatch.model_validate(dict(title='x',questions=[item(1)])).questions[0]
        await reviewer.verify([question],topic='Reasoning')
        self.assertNotIn('correct_option_id',str(llm.ainvoke.call_args.args[1]))
        self.assertEqual(stored_question(question,'id')['validation']['semantic_review'],'model_cross_checked')
        await reviewer.verify([question],topic='Reasoning');self.assertEqual(llm.ainvoke.await_count,1)
        question.prompt+=' New task.'
        await reviewer.verify([question],topic='Reasoning');self.assertEqual(llm.ainvoke.await_count,2)

    async def test_wrong_key_ambiguity_scope_explanation_and_unchanged_challenge_are_rejected(self):
        for changes in [dict(answer_ids=['b']),dict(answer_ids=[]),dict(answerable=False),dict(explanation_valid=False),
                dict(scope_preserved=False),dict(requested_change_met=False),dict(confidence=.4)]:
            with self.subTest(changes=changes):
                reviewer=ChoiceReviewer(SimpleNamespace(ainvoke=AsyncMock(return_value=ChoiceReviewBatch(items=[verdict(**changes)]))))
                q=GeneratedAssessmentBatch.model_validate(dict(title='x',questions=[item(1)])).questions[0]
                with self.assertRaises(GenerationMismatch):await reviewer.verify([q],topic='Reasoning',direction='harder',originals=[dict(prompt='Old')])

    async def test_model_cannot_forge_server_only_cross_check_receipt(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):GeneratedAssessmentBatch.model_validate(dict(title='x',questions=[dict(item(1),_choice_reviewed=True)]))

    async def test_written_revision_false_premise_and_confused_key_are_rejected(self):
        for changes in (dict(answerable=False),dict(explanation_valid=False)):
            question=dict(item(1),question_type='short_answer',answer_mode='text',options=[],correct_option_id=None)
            q=GeneratedAssessmentBatch.model_validate(dict(title='x',questions=[question])).questions[0]
            llm=SimpleNamespace(ainvoke=AsyncMock(side_effect=[IndependentSolutionBatch(items=[dict(position=1,answer_ids=[],answerable=True,solution='Independent answer',confidence=1)]),ChoiceReviewBatch(items=[verdict(answer_ids=[],**changes)])]))
            with self.assertRaises(GenerationMismatch):
                await ChoiceReviewer(llm).verify([q],topic='Joining',direction='harder',originals=[dict(prompt='Old')])
            self.assertEqual(llm.ainvoke.call_args.args[1]['questions'][0]['rubric'],q.rubric)
            blind=llm.ainvoke.call_args_list[0].args[1]['questions'][0]
            self.assertNotIn('explanation',blind);self.assertNotIn('rubric',blind)

    async def test_unavailable_check_retries_the_check_without_regenerating_content(self):
        q=GeneratedAssessmentBatch.model_validate(dict(title='x',questions=[item(1)])).questions[0]
        llm=SimpleNamespace(ainvoke=AsyncMock(side_effect=[ValueError('malformed'),ChoiceReviewBatch(items=[verdict()])]))
        await ChoiceReviewer(llm).verify([q],topic='Reasoning')
        self.assertEqual(llm.ainvoke.await_count,2)
        self.assertTrue(all(call.args[0] is PromptSource.ASSESSMENT_CHOICE_REVIEW for call in llm.ainvoke.call_args_list))

    async def test_missing_review_positions_retry_the_check_then_fail_closed(self):
        from app.core.exceptions import AppError
        q=GeneratedAssessmentBatch.model_validate(dict(title='x',questions=[item(1),item(2)])).questions
        llm=SimpleNamespace(ainvoke=AsyncMock(return_value=ChoiceReviewBatch(items=[verdict()])))
        with self.assertRaises(AppError) as error:await ChoiceReviewer(llm).verify(q,topic='Reasoning')
        self.assertEqual(error.exception.code,'ASSESSMENT_REVIEW_UNAVAILABLE')
        self.assertEqual(llm.ainvoke.await_count,2)
        self.assertFalse(any(item._choice_reviewed for item in q))

    async def test_claimed_change_needs_a_specific_operation_difference(self):
        for changes in (dict(change_kind='unchanged'),dict(change_basis='')):
            q=GeneratedAssessmentBatch.model_validate(dict(title='x',questions=[item(1)])).questions[0]
            llm=SimpleNamespace(ainvoke=AsyncMock(return_value=ChoiceReviewBatch(items=[verdict(**changes)])))
            with self.assertRaises(GenerationMismatch):
                await ChoiceReviewer(llm).verify([q],topic='Naming',direction='harder',originals=[dict(prompt='Old')])

    async def test_failed_independent_check_repairs_only_the_rejected_item(self):
        first=GeneratedAssessmentBatch.model_validate(dict(title='Keep',questions=[item(1),item(2)]))
        replacement=GeneratedAssessmentBatch.model_validate(dict(title='Ignore',questions=[item('new')]))
        llm=SimpleNamespace(ainvoke=AsyncMock(side_effect=[first,
            ChoiceReviewBatch(items=[verdict(),verdict(2,answer_ids=['b'])]),replacement,
            ChoiceReviewBatch(items=[verdict()])]))
        reviewer=ChoiceReviewer(llm)
        plan=[dict(question_type='mcq',answer_mode='single_choice',marks=1)]*2
        async def review(result):await reviewer.verify(result.questions,topic='Reasoning')
        def validate(result):validate_questions(result,count=2,question_format='mcq',concepts=None,tokens=set(),grounded=False,previous=[],plan=plan)
        result=await invoke_generated(llm,PromptSource.ASSESSMENT_GENERATION,dict(count=2,question_format='mcq',question_plan=plan),
            output_schema=GeneratedAssessmentBatch,validate=validate,review=review)
        self.assertEqual(result.title,'Keep');self.assertEqual(result.questions[0].prompt,first.questions[0].prompt)
        self.assertEqual(llm.ainvoke.call_args_list[2].args[1]['repair_positions'],[2])
        self.assertTrue(all(q._choice_reviewed for q in result.questions))

    def test_complete_revision_reuses_public_structure_without_copying_an_oversized_old_key(self):
        from uuid import uuid4
        from app.assessments.schemas import GenerationRequest
        from app.assessments.revision import reusable_revision
        q=dict(item(1),id=str(uuid4()),answer_mode='single_choice',source_tokens=[])
        q['options']=[dict(id=str(i),label=f'Old option {i}') for i in range(7)]
        source=dict(questions=[q],preferences=dict(level=None),paper=None)
        request=GenerationRequest(client_request_id=uuid4(),context_id='scope',topic='Reasoning',count=1,
            question_format='mcq',revision_assessment_id=uuid4(),revision_instructions='Make this harder')
        result=reusable_revision(request,source)
        self.assertEqual(result['positions'],[0]);self.assertEqual(result['retained'],[None])
        self.assertEqual(result['plan'][0]['answer_mode'],'single_choice')
        self.assertNotIn('options',result['plan'][0]);self.assertNotIn('correct_option_id',result['plan'][0])
        self.assertEqual(len(source['questions'][0]['options']),7)
