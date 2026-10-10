"""Deterministic tool-capable inference for integration/browser tests only."""
import json
from langchain_core.messages import AIMessage, ToolMessage
from testing.rag import TestChatFactory


class HistoryChatFactory(TestChatFactory):
    def bind_tools(self, tools, **kwargs):
        self.final_schema = next((tool for tool in tools if isinstance(tool,type) and tool.__name__=='NewChatReply'),None)
        self.announced_tools = {tool.name for tool in tools if not isinstance(tool,type) and 'user_message' in tool.args_schema.model_fields}
        return self

    def tool_call(self, name, args, identifier):
        if name in getattr(self, 'announced_tools', set()):
            from app.langchain.tool_activity import LABELS
            args = dict(args, tool_name=name, user_message=LABELS[name])
        return dict(name=name, args=args, id=identifier, type='tool_call')

    def with_structured_output(self, schema, **kwargs):
        class Structured:
            async def ainvoke(self, messages):
                data = json.loads(messages[-1].content)
                if schema.__name__ == 'GeneratedAssessment':
                    revised = bool(data.get('revision_instructions'))
                    return schema(title=('Revised: ' if revised else 'Practice: ')+data['topic'], questions=[dict(prompt=f'{"Explain simply" if revised else "Explain"} {data["targets"][0]["name"]} ({data.get("question_offset",0)+index+1}).', concept_ids=[data['targets'][0]['id']], difficulty=.2 if revised else .4, marks=2, model_answer='A supported explanation.', rubric='Award partial credit for an accurate explanation.', source_tokens=[data['sources'][0]['token']] if data.get('sources') else []) for index in range(data['count'])])
                if schema.__name__ == 'GradedAssessment':
                    return schema(questions=[dict(question_id=question['id'], score=1, confidence=.95,
                        feedback='A useful partial explanation. Add the missing detail.',
                        concept_grades={concept:dict(score=1,max_score=question['marks'],confidence=.95) for concept in question['concept_ids']}) for question in data['questions']])
                text = data['user_message'].lower()
                conflicts = [x['id'] for x in data.get('existing', []) if 'favorite color' in text and 'favorite color' in x['content'].lower() and x['content'] != data['claim']]
                return schema(supported=not any(x in text for x in ['if i', 'someone said', 'do not remember']),
                    explicit_user_statement=not text.startswith('maybe'), sensitive='diagnosis' in text,
                    explicit_remember_request=text.startswith('remember'), durable=True, contradicts_existing=bool(conflicts), conflicting_memory_ids=conflicts)
        return Structured()

    async def ainvoke(self, messages):
        response = await self._respond(messages)
        if getattr(self,'final_schema',None) is not None and not response.tool_calls:
            question = next((str(item.content) for item in messages if item.type=='human'),'New chat')
            return AIMessage(content='',tool_calls=[dict(name='NewChatReply',args=dict(content=response.content,
                conversation_title=' '.join(question.split()[:8])[:80] or 'New chat'),id='final-answer',type='tool_call')])
        return response

    async def _respond(self, messages):
        results = [x for x in messages if isinstance(x, ToolMessage)]
        if results:
            result = json.loads(results[-1].content)
            if results[-1].name == 'get_active_learning_contexts':
                context = next(item for item in result['contexts'] if item['name']=='Algebra')
                return AIMessage(content='',tool_calls=[self.tool_call('assessment_generate',
                    dict(context_id=context['context_id'],topic='Linear equations',count=2), 'assessment-generate')])
            if (results[-1].name or '').startswith('assessment_'):
                return AIMessage(content=result.get('reason', result.get('next_step', 'Your assessment is ready in the chat card.')))
            if 'memories' in result:
                return AIMessage(content='Your saved preference is ' + result['memories'][0]['content'] + ' [['+result['memories'][0]['token']+']]' if result['memories'] else 'No saved memories matched.')
            if 'windows' in result:
                return AIMessage(content='Found the past exchange. [['+result['windows'][0]['token']+']]' if result['windows'] else 'No past exchanges matched.')
            return AIMessage(content='Memory saved.' if result.get('outcome') in ('saved','already_known') else 'Memory '+result.get('outcome','unavailable')+'. Review it in Settings.')
        question = next((str(x.content) for x in reversed(messages) if x.type == 'human'), '')
        lowered = question.lower()
        if lowered.startswith('my algebra exam is on october 20'):
            user = next(message for message in reversed(messages) if message.type == 'human')
            return AIMessage(content='', tool_calls=[self.tool_call('event_manage', dict(message_id=user.id,
                quote=question, candidate=dict(title='Algebra exam', kind='exam', timezone='UTC', local_date='2026-10-20')), 'event-create')])
        system = str(messages[0].content)
        marker = system.rfind('\n\n{')
        context = json.loads(system[marker+2:]) if marker >= 0 else {}
        scope = context.get('history_scope')
        if scope:
            if lowered.startswith('generate a two question quiz'):
                return AIMessage(content='',tool_calls=[self.tool_call('get_active_learning_contexts',{},'assessment-context')])
            if lowered.startswith('explain question 1') and context.get('chat_assessments'):
                return AIMessage(content='',tool_calls=[self.tool_call('assessment_question',
                    dict(draft_id=context['chat_assessments'][0]['draft_id'],number=1),'assessment-question')])
            if lowered.startswith('make this assessment easier') and context.get('chat_assessments'):
                return AIMessage(content='',tool_calls=[self.tool_call('assessment_revise',
                    dict(draft_id=context['chat_assessments'][0]['draft_id'],instructions=question),'assessment-revise')])
            if lowered.startswith('evaluate these answers:') and context.get('chat_assessments'):
                import re
                answers = dict(re.findall(r'(?m)^(\d+)\. (.+)$',question))
                return AIMessage(content='',tool_calls=[self.tool_call('assessment_answer',
                    dict(draft_id=context['chat_assessments'][0]['draft_id'],answers=answers), 'assessment-answer')])
            if lowered.startswith('evaluate this answer sheet') and context.get('chat_assessments'):
                return AIMessage(content='',tool_calls=[self.tool_call('assessment_answer',
                    dict(draft_id=context['chat_assessments'][0]['draft_id'],attachment_id=context['assessment_answer_attachments'][0]), 'assessment-upload')])
            if lowered.startswith(('remember', 'maybe')):
                return AIMessage(content='', tool_calls=[self.tool_call('user_memory', dict(action='remember', content=question,
                    category='preference', evidence_message_id=scope['current_user_message_id'], evidence_quote=question), 'remember_call')])
            if lowered.startswith('recall memories about '):
                return AIMessage(content='', tool_calls=[self.tool_call('user_memory', dict(action='recall', query=question[22:]), 'recall_call')])
            if lowered.startswith('find past chats about '):
                return AIMessage(content='', tool_calls=[self.tool_call('history_lookup', dict(scope='all_chats', query=question[22:]), 'history_call')])
        return await super().ainvoke(messages)
