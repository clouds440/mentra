"""Visible-artifact edits and accepted-assessment reuse, without paid calls."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from langchain_core.messages import AIMessage, HumanMessage
from app.assessments.schemas import GenerationRequest, GeneratedQuestion, GeneratedAssessmentBatch
from app.assessments.revision import reusable_revision
from app.langchain.planning import plan_request
from app.langchain.history_orchestration import tool_reply
from app.langchain.assessment_workflows import AssessmentWorkflows


def history(content='```tsx\nexport const Button = () => <button>Save</button>;\n```'):
    return [dict(id='u1',role='user',content='Create a React button'),
            dict(id='a1',role='assistant',content=content,metadata={})]


class FollowupRoutingTests(unittest.TestCase):
    def test_visible_edits_select_no_domain_tools(self):
        for query in ('Change its click event to call onSave', 'Make it shorter',
                      'Rewrite the email in a warmer tone', 'Add a limitations section',
                      'Change the essay conclusion', 'Keep the same API but add a disabled state'):
            plan=plan_request(query,context_rows=history(),selected_sources=True)
            self.assertTrue(plan.direct_candidate,query)
            self.assertEqual(plan.edit_source_id,'a1')
            self.assertEqual(plan.tool_names,[])
            self.assertEqual(plan.required_domains,[])

    def test_external_actions_missing_originals_and_cards_are_not_text_edits(self):
        for query in ('Change my schedule', 'Update my profile', 'Revise using my notes', 'Update it with the latest research'):
            self.assertIsNone(plan_request(query,context_rows=history()).edit_source_id,query)
        self.assertIsNone(plan_request('Make it shorter').edit_source_id)
        rows=history();rows[-1]['metadata']={'assessment_cards':[{'id':'draft'}]}
        plan=plan_request('Make question 2 clearer',context_rows=rows)
        self.assertEqual(plan.tool_names,['assessment_revise'])
        self.assertEqual(plan.required_outcome,'assessment')


class VisibleEditTests(unittest.IsolatedAsyncioTestCase):
    async def test_web_research_edit_reuses_validated_links_without_search(self):
        from app.langchain.chat_service import ChatService
        from app.web_search.urls import favicon_url
        rows=history('Existing research finding. [[W1]]')
        rows[-1]['metadata']={'web_sources':[dict(token='W1',url='https://example.org/paper',domain='example.org',
            favicon_url=favicon_url('example.org'),title='Original paper',excerpt='Original finding',searched_at='2026-10-26T00:00:00Z')]}
        query='Make the research paper shorter'
        state=dict(execution_plan=plan_request(query,context_rows=rows),context_rows=rows,current_answer_text=query,
                   current_user_message_id='u2',user_sequence=3,history_references=[],memory_references=[])
        self.assertEqual(state['execution_plan'].edit_source_id,'a1')
        model=SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='',tool_calls=[dict(name='DirectAnswer',
            id='a',args=dict(content='Short finding. [Source W1](https://example.org/paper)',general_query=True,needs_tools=False,uncertain=False))])))
        chat=ChatService.__new__(ChatService);chat._llm=model
        await chat.reply([(row['role'],row['content']) for row in rows]+[('user',query)],history_runtime=(None,str(uuid4()),state))
        self.assertEqual(model.ainvoke_messages.await_count,1)
        messages=model.ainvoke_messages.call_args.args[1]
        original=next(message for message in messages if message.id=='a1')
        self.assertIn('[Source W1](<https://example.org/paper>)',original.content)
        self.assertEqual(rows[-1]['content'],'Existing research finding. [[W1]]')

    async def test_complete_latest_original_survives_small_history_budget_in_one_call(self):
        original='```tsx\n'+(' // keep this existing implementation\n'*90)+'export const Button = () => <button>Save</button>;\n```'
        rows=history(original)
        query='Change its click event to call onSave'
        plan=plan_request(query,context_rows=rows)
        state=dict(execution_plan=plan,context_rows=rows,current_answer_text=query,current_user_message_id='u2',
                   user_sequence=3,history_references=[],memory_references=[],history_token_budget=256)
        revised='```tsx\nexport const Button = ({ onSave }) => <button onClick={onSave}>Save</button>;\n```'
        model=SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='',tool_calls=[dict(
            name='DirectAnswer',id='answer',args=dict(content=revised,general_query=True,needs_tools=False,uncertain=False))])))
        result=await tool_reply(model,[HumanMessage(content=rows[0]['content'],id='u1'),AIMessage(content=original,id='a1'),
                                      HumanMessage(content=query,id='u2')],None,str(uuid4()),state,(),{})
        self.assertEqual(result.content,revised)
        self.assertEqual(model.ainvoke_messages.await_count,1)
        messages=model.ainvoke_messages.call_args.args[1]
        self.assertTrue(any(message.id=='a1' and message.content==original for message in messages))
        self.assertEqual([getattr(tool,'name',getattr(tool,'__name__','')) for tool in model.ainvoke_messages.call_args.kwargs['tools']],['enable_workflow_tools','DirectAnswer'])

    async def test_private_revision_source_remains_owned_and_conversation_scoped(self):
        from app.assessments.service import AssessmentService
        from app.core.exceptions import AppError
        service=AssessmentService.__new__(AssessmentService)
        source=dict(context_id='context',questions=[question(1)])
        service.chat=SimpleNamespace(revision_source=Mock(return_value=dict(conversation_id='other-chat',assessment=source)))
        request=GenerationRequest(client_request_id=uuid4(),context_id='context',topic='Practice',revision_draft_id=uuid4(),revision_instructions='Make it clearer')
        with self.assertRaises(AppError) as rejected:
            await service._revision_source('owner',request,'this-chat')
        self.assertEqual(rejected.exception.code,'ASSESSMENT_DRAFT_NOT_FOUND')
        self.assertEqual(service.chat.revision_source.call_args.args[0],'owner')


def question(index):
    return GeneratedQuestion(question_type='mcq',prompt=f'Original question {index}',concept_ids=['accepted-concept'],
        difficulty=.4,marks=1,options=[dict(id='a',label='One'),dict(id='b',label='Two')],correct_option_id='a',
        model_answer='One',rubric='Award 1 mark only for a.').model_dump()


class AcceptedRevisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_visible_card_edit_needs_one_routing_call_and_no_lookup_tool(self):
        owner=str(uuid4());conversation=str(uuid4());draft=str(uuid4())
        source=dict(title='Practice',context_id='context',purpose='practice',preferences={},paper=None,sources=[],questions=[question(1),question(2)])
        card=dict(id=draft,conversation_id=conversation,assessment_id=None,assessment=source)
        query='Make question 2 clearer'
        rows=history();rows[-1]['metadata']={'assessment_cards':[card]}
        service=SimpleNamespace(chat=SimpleNamespace(detail=Mock(return_value=card)),generate_chat=AsyncMock(return_value=dict(
            card,id=str(uuid4()),assessment=dict(source,title='Practice revised'))))
        state=dict(execution_plan=plan_request(query,context_rows=rows),assessment_service=service,current_answer_text=query,
            current_user_message_id=str(uuid4()),conversation_id=conversation,user_sequence=3,context_rows=rows,history_references=[],memory_references=[])
        model=SimpleNamespace(ainvoke_messages=AsyncMock(return_value=AIMessage(content='',tool_calls=[dict(name='assessment_revise',
            id='revise',args=dict(draft_id=draft,instructions=query,question_numbers=['2']))])))
        reply=await tool_reply(model,[HumanMessage(content=query)],None,owner,state,(),{})
        self.assertEqual(model.ainvoke_messages.await_count,1)
        self.assertEqual(reply.content,'Practice revised')
        self.assertEqual(service.generate_chat.call_args.args[2].revision_question_numbers,['2'])
        self.assertNotIn('assessment_lookup',[getattr(tool,'name','') for tool in model.ainvoke_messages.call_args.kwargs['tools']])

    def test_retrieval_cannot_reassign_an_unchanged_questions_citation(self):
        from app.assessments.revision import revision_sources
        old=dict(token='S1',document_id='old-doc',version_id='v1',generation_id='g1',chunk_id='c1',excerpt='Original evidence')
        new=dict(token='S1',document_id='new-doc',version_id='v2',generation_id='g2',chunk_id='c2',excerpt='Fresh evidence')
        merged=revision_sources([old],[new,old])
        self.assertEqual(merged,[old,dict(new,token='S2')])
        self.assertEqual(new['token'],'S1')

    async def test_one_of_twenty_reuses_nineteen_private_items_and_one_content_call(self):
        original=dict(title='Existing practice',context_id='context',preferences={},paper=None,
                      questions=[question(index) for index in range(1,21)])
        snapshot=copy.deepcopy(original)
        request=GenerationRequest(client_request_id=uuid4(),context_id='context',topic='Existing practice',count=20,
            question_format='mcq',revision_draft_id=uuid4(),revision_instructions='Make question 2 clearer',
            instructions='Make question 2 clearer',revision_question_numbers=['2'])
        payloads=[]
        class Model:
            async def ainvoke(self,source,payload,**kwargs):
                self.assert_source=source.value
                if source.value!='assessment_generation': raise AssertionError('Unnecessary model stage')
                payloads.append(payload)
                return GeneratedAssessmentBatch(title='Existing practice revised',questions=[dict(question(2),prompt='Clearer question two')])
        resolve=AsyncMock()
        learner=SimpleNamespace(get_context_summaries=lambda *a:[],
            get_study_targets=Mock(side_effect=AssertionError('Do not rerank accepted practice for a wording edit')),
            get_concepts=lambda ids:{identifier:SimpleNamespace(canonical_name='Accepted concept') for identifier in ids},
            get_relevant_context=Mock(side_effect=AssertionError('Do not reload mastery for a wording edit')),resolve_generated_concepts=resolve)
        result,_=await AssessmentWorkflows(Model(),learner).generate(str(uuid4()),request,revision=original)
        self.assertEqual(len(payloads),1)
        self.assertEqual(payloads[0]['count'],1)
        self.assertEqual(len(payloads[0]['original_questions']),1)
        self.assertNotIn('model_answer',str(payloads[0]['original_questions']))
        self.assertEqual(len(result.questions),20)
        for index,item in enumerate(result.questions):
            self.assertEqual(item.model_dump(),dict(question(index+1),prompt='Clearer question two') if index==1 else question(index+1))
        self.assertEqual(original,snapshot)
        resolve.assert_not_awaited()

    def test_structure_changes_and_unknown_references_do_not_silently_reuse(self):
        original=dict(preferences={},paper=None,questions=[question(1),question(2)])
        body=dict(client_request_id=uuid4(),context_id='context',topic='Practice',count=2,question_format='mcq',
                  revision_draft_id=uuid4(),revision_instructions='Make question 2 clearer')
        self.assertIsNone(reusable_revision(GenerationRequest(**dict(body,count=3)),original))
        with self.assertRaisesRegex(Exception,'Choose question references'):
            reusable_revision(GenerationRequest(**body,revision_question_numbers=['99']),original)
