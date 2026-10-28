"""Explicit, bounded serializable state between chat graph nodes."""
import json
from langchain_core.messages import messages_to_dict, messages_from_dict, HumanMessage
from app.chat.response import ChatResponse

POLICY_VERSION = 'semantic-v3'
PUBLIC = ('history_references', 'memory_references', 'event_references', 'event_proposals',
          'assessment_cards', 'interactions', 'web_sources', 'web_searches')
PRIVATE = ('_tool_execution_state', '_assessment_receipt', '_captured_events', '_ui_topics',
           '_memory_summary_fence', 'tool_warnings', 'retrieval_status', 'retrieval_warnings',
           'retrieval_context_ids', 'visible_ids', 'history_references', 'memory_references',
           '_domain_tool_used', 'direct_rejected', '_task_receipts', '_selected_operations', '_committed_tool_results', 'response_outcome',
           '_web_cache', '_research_cache', '_web_physical_calls', '_research_physical_calls')


class ResponseRuntime:
    def __init__(self, conversation, scope, budget, selection, executor):
        self.conversation, self.scope, self.budget = conversation, scope, budget
        self.selection, self.executor = selection, executor
        self.needs_validation = False

    async def validate(self):
        if not self.needs_validation:
            return
        checkpoint = self.scope.get('_response_checkpoint')
        if checkpoint:
            from sqlalchemy.orm import Session
            from app.history_management.repositories.postgres import MemoryRepository
            from app.core.observability.timing import run_in_threadpool
            from app.core.exceptions import AppError
            engine,owner,_ = checkpoint
            def check():
                with Session(engine) as session:
                    return MemoryRepository.references_current(session,owner,self.scope)
            if not await run_in_threadpool(check):
                raise AppError('CHAT_RESUME_CONTEXT_CHANGED','Saved sources changed. Retry with the current information.',409)
            rag = self.scope.get('rag_service')
            if rag:
                selection = self.scope.get('retrieval_selection')
                for source in self.scope.get('study_sources',[]):
                    await run_in_threadpool(rag.get_chunk,owner,source.chunk_id,getattr(selection,'include_archived',False))
        self.needs_validation = False

    def capture(self, amendment=None):
        if amendment:
            self.conversation.append(HumanMessage(content='Continue the paused response with this requested change: ' + amendment))
            self.scope['_assessment_receipt'] = None
        payload = {key: self.scope[key] for key in (*PUBLIC, *PRIVATE) if key in self.scope}
        from .concurrent_reads import StagedRead
        if '_tool_execution_state' in payload:
            execution = payload['_tool_execution_state']
            # Projectors are closures bound to this invocation. Persist data,
            # then reauthorize/reproject it through the domain on restoration.
            payload['_tool_execution_state'] = dict(execution, results={key:value for key,value in execution.get('results',{}).items() if not isinstance(value,StagedRead)})
        payload['sources'] = self.scope.get('study_sources', [])
        payload['evidence_ids'] = list(self.scope.get('evidence_ids', []))
        # Store only data, never service objects, closures, coroutines or source
        # selection permissions. Explicit sources are revalidated on every run.
        payload = json.loads(json.dumps(payload, default=lambda value: value.model_dump(mode='json')))
        return dict(policy_version=POLICY_VERSION, attempt=self.scope.get('attempt',1), conversation=messages_to_dict(self.conversation), scope=payload,
            active=sorted(self.selection.active), pending=sorted(self.selection.pending), explicit=sorted(getattr(self.selection,'explicit',())),
            budget={key:getattr(self.budget, key) for key in
                ('calls', 'writes', 'presentations', 'result_characters', 'result_tokens', 'delivered')})

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
        if value.get('policy_version')!=POLICY_VERSION:
            payload['tool_warnings']=[item for item in payload.get('tool_warnings',[]) if item.get('code')!='REQUEST_OUTCOME_INCOMPLETE']
        public = ChatResponse(role='assistant', content='', **{key:payload[key] for key in (*PUBLIC, 'sources') if key in payload})
        for key in PUBLIC:
            if key in payload: payload[key] = getattr(public, key)
        if 'interactions' in payload:
            payload['interactions'] = [card.model_dump(mode='json') for card in public.interactions]
        self.scope['study_sources'] = public.sources
        payload.pop('sources', None)
        payload['evidence_ids'] = set(payload.get('evidence_ids', []))
        self.scope.update(payload)
        from .recovery_receipts import restore_recovery
        restore_recovery(self.scope)
        state = self.scope.get('_tool_execution_state', {})
        new_attempt = value.get('attempt',1) != self.scope.get('attempt',1)
        if new_attempt:
            self.needs_validation = True
            state['failed'] = {key:receipt for key,receipt in state.get('failed',{}).items()
                if not (receipt.get('retryable') or receipt.get('category') == 'budget_exhausted') or receipt.get('effect_certainty') not in ('read_only','not_started')}
            state['outages'] = {}
            state['results'] = {key:result for key,result in state.get('results',{}).items()
                if key.split(':',1)[0] in ('web_search','web_research')}
        self.executor.failed = state.get('failed', {})
        self.executor.results = state.get('results', {})
        self.executor.outages = state.get('outages', {})
        self.selection.active = set(value['active']) & self.selection.by_name.keys()
        if value.get('policy_version')!=POLICY_VERSION:
            self.selection.active.update(self.selection.common)
        self.selection.explicit = set(value.get('explicit', [])) & self.selection.by_name.keys()
        self.selection.pending = set(value['pending']) & self.selection.explicit
        for key, amount in value['budget'].items():
            if not new_attempt or key == 'delivered': setattr(self.budget, key, amount)
