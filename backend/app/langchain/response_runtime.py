"""Explicit, bounded serializable state between chat graph nodes."""
import json
from langchain_core.messages import messages_to_dict, messages_from_dict, HumanMessage
from app.chat.response import ChatResponse

POLICY_VERSION = 'conversation-assessment-v2'
PUBLIC = ('history_references', 'memory_references', 'event_references', 'event_proposals',
          'assessment_cards', 'interactions', 'web_sources', 'web_searches')
PRIVATE = ('_tool_execution_state', '_assessment_receipt', '_captured_events', '_ui_topics',
           '_memory_summary_fence', 'tool_warnings', 'retrieval_status', 'retrieval_warnings',
           'retrieval_context_ids', 'visible_ids', 'history_references', 'memory_references',
           '_domain_tool_used', 'direct_rejected')


class ResponseRuntime:
    def __init__(self, conversation, scope, budget, selection, executor):
        self.conversation, self.scope, self.budget = conversation, scope, budget
        self.selection, self.executor = selection, executor

    def capture(self, amendment=None):
        if amendment:
            self.conversation.append(HumanMessage(content='Continue the paused response with this requested change: ' + amendment))
            self.scope['_assessment_receipt'] = None
        payload = {key: self.scope[key] for key in (*PUBLIC, *PRIVATE) if key in self.scope}
        payload['sources'] = self.scope.get('study_sources', [])
        payload['evidence_ids'] = list(self.scope.get('evidence_ids', []))
        # Store only data, never service objects, closures, coroutines or source
        # selection permissions. Explicit sources are revalidated on every run.
        payload = json.loads(json.dumps(payload, default=lambda value: value.model_dump(mode='json')))
        return dict(policy_version=POLICY_VERSION, conversation=messages_to_dict(self.conversation), scope=payload,
            active=sorted(self.selection.active), pending=sorted(self.selection.pending),
            budget={key:getattr(self.budget, key) for key in
                ('calls', 'writes', 'result_characters', 'result_tokens', 'delivered')})

    def restore(self, value):
        previous = value['scope'].get('_memory_summary_fence')
        current = self.scope.get('_memory_summary_fence')
        if previous is not None and previous != current:
            from app.core.exceptions import AppError
            raise AppError('CHAT_RESUME_CONTEXT_CHANGED', 'Saved memories changed. Retry this response to use current context.', 409)
        self.conversation[:] = messages_from_dict(value['conversation'])
        if value.get('policy_version') != POLICY_VERSION:
            # Old checkpoints may contain a router repair demanding an
            # assessment for an ordinary conversation. Reapply current policy;
            # retain user messages, tool results and completed domain receipts.
            # System context is rebuilt by tool_reply, outside this transcript.
            self.conversation[:] = [message for message in self.conversation if message.type != 'system']
        payload = dict(value['scope'])
        public = ChatResponse(role='assistant', content='', **{key:payload[key] for key in (*PUBLIC, 'sources') if key in payload})
        for key in PUBLIC:
            if key in payload: payload[key] = getattr(public, key)
        if 'interactions' in payload:
            payload['interactions'] = [card.model_dump(mode='json') for card in public.interactions]
        self.scope['study_sources'] = public.sources
        payload.pop('sources', None)
        payload['evidence_ids'] = set(payload.get('evidence_ids', []))
        self.scope.update(payload)
        state = self.scope.get('_tool_execution_state', {})
        self.executor.failed = state.get('failed', {})
        self.executor.results = state.get('results', {})
        self.executor.outages = state.get('outages', {})
        self.selection.active = set(value['active']) & self.selection.by_name.keys()
        self.selection.pending = set(value['pending']) & self.selection.by_name.keys()
        for key, amount in value['budget'].items(): setattr(self.budget, key, amount)
