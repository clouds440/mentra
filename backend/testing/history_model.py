"""Deterministic tool-capable inference for integration/browser tests only."""
import json
from langchain_core.messages import AIMessage, ToolMessage
from testing.rag import TestChatFactory


class HistoryChatFactory(TestChatFactory):
    def bind_tools(self, tools):
        return self

    def with_structured_output(self, schema, **kwargs):
        class Structured:
            async def ainvoke(self, messages):
                data = json.loads(messages[-1].content)
                text = data['user_message'].lower()
                conflicts = [x['id'] for x in data.get('existing', []) if 'favorite color' in text and 'favorite color' in x['content'].lower() and x['content'] != data['claim']]
                return schema(supported=not any(x in text for x in ['if i', 'someone said', 'do not remember']),
                    explicit_user_statement=not text.startswith('maybe'), sensitive='diagnosis' in text,
                    explicit_remember_request=text.startswith('remember'), durable=True, contradicts_existing=bool(conflicts), conflicting_memory_ids=conflicts)
        return Structured()

    async def ainvoke(self, messages):
        results = [x for x in messages if isinstance(x, ToolMessage)]
        if results:
            result = json.loads(results[-1].content)
            if 'memories' in result:
                return AIMessage(content='Your saved preference is ' + result['memories'][0]['content'] + ' [['+result['memories'][0]['token']+']]' if result['memories'] else 'No saved memories matched.')
            if 'windows' in result:
                return AIMessage(content='Found the past exchange. [['+result['windows'][0]['token']+']]' if result['windows'] else 'No past exchanges matched.')
            return AIMessage(content='Memory saved.' if result.get('outcome') in ('saved','already_known') else 'Memory '+result.get('outcome','unavailable')+'. Review it in Settings.')
        question = next((str(x.content) for x in reversed(messages) if x.type == 'human'), '')
        lowered = question.lower()
        system = str(messages[0].content)
        marker = system.rfind('\n\n{')
        context = json.loads(system[marker+2:]) if marker >= 0 else {}
        scope = context.get('history_scope')
        if scope:
            if lowered.startswith(('remember', 'maybe')):
                return AIMessage(content='', tool_calls=[dict(name='user_memory', args=dict(action='remember', content=question,
                    category='preference', evidence_message_id=scope['current_user_message_id'], evidence_quote=question), id='remember_call', type='tool_call')])
            if lowered.startswith('recall memories about '):
                return AIMessage(content='', tool_calls=[dict(name='user_memory', args=dict(action='recall', query=question[22:]), id='recall_call', type='tool_call')])
            if lowered.startswith('find past chats about '):
                return AIMessage(content='', tool_calls=[dict(name='history_lookup', args=dict(scope='all_chats', query=question[22:]), id='history_call', type='tool_call')])
        return await super().ainvoke(messages)
