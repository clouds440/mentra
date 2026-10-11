import re
import json
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from app.rag.schemas import SearchRequest, ChatSelection
from app.langchain.chat_service import ChatService
from app.chat.context import HistoryContextPolicy
from app.langchain.prompts import PromptSource, get_system_prompt
from app.chat.response import ChatResponse
from .activity import ActivityPublisher
from app.learner.schemas import LearnerContextRequest


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class OrchestrationService:
    """Shared AI coordination boundary; domain services retain validation and writes."""
    def __init__(self, chat, *, rag=None, learner=None, history=None, attachments=None, event_proposals=None, assessments=None, web_search=None):
        self.chat, self.rag, self.learner, self.history = chat, rag, learner, history
        self.attachments = attachments
        self.event_proposals = event_proposals
        self.assessments = assessments
        self.web_search = web_search

    async def generate_assessment(self, owner, request):
        if self.assessments is None: raise AppError('ASSESSMENT_UNAVAILABLE', 'Assessments are unavailable.', 503)
        return await self.assessments.generate(owner, request)

    async def chat_reply(self, messages, retrieval, owner, history_policy=None, history_scope=None):
        from .workflow_budget import model_budget
        from .activity import publish_activity
        publisher = history_scope.get('activity', ActivityPublisher()) if history_scope else ActivityPublisher()
        with model_budget(deadline=history_scope.get('_generation_deadline') if history_scope else None), publish_activity(publisher):
            return await self._chat_reply(messages, retrieval, owner, history_policy, history_scope)

    async def _chat_reply(self, messages, retrieval, owner, history_policy=None, history_scope=None):
        if history_scope is None and self.web_search is not None and self.web_search.enabled and owner:
            from uuid import uuid4
            rows = [dict(id=str(uuid4()), role=role, content=content) for role, content in messages]
            history_scope = dict(context_rows=rows, current_user_message_id=next((row['id'] for row in reversed(rows) if row['role'] == 'user'), str(uuid4())),
                visible_ids=[], evidence_ids=set(), history_references=[], memory_references=[], user_sequence=0, stateless=True)
        activity = history_scope.get('activity', ActivityPublisher()) if history_scope else ActivityPublisher()
        recovery_scope = history_scope if history_scope is not None else {}
        from app.history_management.budgets import ToolBudget
        from .tool_execution import ToolExecutor
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel
        budget = recovery_scope.setdefault('_tool_budget', ToolBudget())
        executor = ToolExecutor(budget, recovery_scope, activity)
        class ReadInput(BaseModel):
            request_key: str
        async def read(name, action, *arguments, required=False, timeout=10):
            rejected_input = None
            async def invoke(request_key):
                nonlocal rejected_input
                try:
                    return await run_in_threadpool(action, *arguments)
                except AppError as error:
                    # Reject inaccessible/invalid explicit sources at the API
                    # boundary; a dependency outage can still yield a limited reply.
                    if required and error.status_code in (400, 401, 403, 404, 422) and error.code != 'RAG_QUERY_TOO_LONG':
                        rejected_input = error
                    raise
            from .tool_policy import DOMAINS
            tool = StructuredTool.from_function(name=name, description='Prepare requested context', args_schema=ReadInput, coroutine=invoke, metadata={'domain': DOMAINS.get(name, 'documents' if name == 'document_extract' else 'profile')})
            result = await executor.execute(tool, {'request_key': json.dumps(arguments, default=str)}, required=required, max_attempts=1 if required or timeout > 10 else 2, timeout=timeout)
            if rejected_input is not None:
                raise rejected_input
            if isinstance(result, dict) and result.get('code') and result.get('outcome') == 'unavailable':
                return None
            return result
        query = next((content for role, content in reversed(messages) if role == 'user'), '')
        from .planning import plan_request
        plan = plan_request(query, attachments=bool(history_scope and history_scope.get('attachment_ids')),
                            selected_sources=bool(retrieval and (retrieval.document_ids or retrieval.context_ids)),
                            context_rows=history_scope.get('context_rows', ()) if history_scope else ())
        modules = {step.module for step in plan.steps}
        required = {step.module for step in plan.steps if step.required}
        recovery_scope['execution_plan'] = plan
        chat_assessments = []
        if self.assessments is not None and history_scope and not history_scope.get('stateless') and 'assessment' in modules:
            chat_assessments = await read('assessment_lookup', self.assessments.chat.recent, owner, history_scope['conversation_id']) or []
        await activity.emit('planning', 'completed', 'Your request is ready to process')
        result, warning = None, None
        if self.rag is not None and 'rag' in modules:
            selection = retrieval.model_dump() if retrieval else {}
            result = await read('search_study_material', self.rag.search, owner, SearchRequest(query=query, **selection), required='rag' in required)
            if result is None:
                warning = 'Study material retrieval was unavailable; document-specific claims cannot be verified.'
                workflow_logger.set_outcome('degraded', code='RAG_UNAVAILABLE')
            else:
                recovery_scope['_initial_search'] = (query, result)
        packet = dict(status=result.status if result else 'unavailable' if warning else 'no_eligible_sources' if 'rag' in modules else 'not_requested',
                      sources=[chunk.source.model_dump() for chunk in result.chunks] if result else [])
        if result and result.warnings:
            workflow_logger.set_outcome('degraded', code='RETRIEVAL_DEGRADED')
            warning = ' '.join(result.warnings)
        kwargs = {'source_packet': packet} if self.rag is not None else {}
        if self.attachments is not None and history_scope and not history_scope.get('stateless'):
            ids = history_scope.get('attachment_ids', [])
            if not ids:
                # Follow-up questions can refer to the latest attached user message.
                for row in reversed(history_scope['context_rows']):
                    if row.get('metadata', {}).get('attachments'):
                        ids = [item['id'] for item in row['metadata']['attachments']][:4]
                        break
            documents = []
            history_scope['assessment_attachment_ids'] = ids
            answer_upload = 'assessment' in modules and bool(re.search(r'\b(grade|evaluate|mark|answers?|solutions?|answer sheet)\b', query, re.I))
            for identifier in ([] if answer_upload or plan.direct_candidate else ids):
                extracted = await read('document_extract', self.attachments.extract, owner, identifier, history_scope['conversation_id'], required='documents' in required, timeout=120)
                if extracted is not None:
                    documents.append(self.attachments.context(extracted, query, maximum=8000 // max(1, len(ids))))
            if documents:
                kwargs['document_context'] = documents
        if self.history is not None and self.history.profile is not None and 'profile' in modules:
            kwargs['profile_context'] = await read('profile_context', self.history.profile.prompt_context, owner)
            if kwargs['profile_context'] is not None:
                kwargs['profile_context'] = kwargs['profile_context'].model_dump(mode='json')
        if self.learner is not None and owner and 'learner' in modules:
            kwargs['learner_context'] = await read('get_relevant_learner_context', self.learner.get_relevant_context, LearnerContextRequest(learner_id=owner, query=query[:4000], context_ids=retrieval.context_ids if retrieval else None))
            if kwargs['learner_context'] is not None:
                recovery_scope['_initial_learner_context'] = kwargs['learner_context'].model_dump(mode='json')
        policy = history_policy or HistoryContextPolicy()
        if history_scope is not None and (self.history is not None or self.web_search is not None and self.web_search.enabled):
            history_scope['activity'] = activity
            history_scope['learner_service'] = self.learner
            history_scope['web_search_service'] = self.web_search
            history_scope['event_proposal_service'] = None if history_scope.get('stateless') else self.event_proposals
            history_scope['workflow_modules'] = modules
            history_scope['rag_service'] = self.rag
            history_scope['assessment_service'] = None if history_scope.get('stateless') else self.assessments
            history_scope['attachment_service'] = None if history_scope.get('stateless') else self.attachments
            history_scope['current_answer_text'] = query
            history_scope['chat_assessments'] = [dict(draft_id=card['id'], assessment_id=card['assessment_id'],
                title=card['assessment']['title'], question_count=len(card['assessment']['questions'])) for card in chat_assessments]
            history_scope['retrieval_selection'] = retrieval or ChatSelection()
            history_scope['study_sources'] = [chunk.source for chunk in result.chunks] if result else []
            async def delta(value):
                await activity.emit('response-stream', 'running', 'Writing your response', token_delta=value, token_reset=value is None)
            history_scope['on_delta'] = delta
            history_scope['history_token_budget'] = policy.max_tokens
            kwargs['history_runtime'] = (None if history_scope.get('stateless') else self.history, owner, history_scope)
        else:
            system_text = get_system_prompt(PromptSource.CHAT)
            if self.rag is not None:
                system_text += '\n\n' + get_system_prompt(PromptSource.RAG_CONTEXT) + '\n\n' + json.dumps({'study_sources': packet}, ensure_ascii=False)
            if kwargs.get('learner_context') is not None:
                system_text += '\n' + kwargs['learner_context'].model_dump_json()
            if kwargs.get('document_context'):
                system_text += '\n' + json.dumps(kwargs['document_context'])
            messages = policy.for_prompt(messages, system_text)
        if recovery_scope.get('tool_warnings'):
            kwargs['recovery_context'] = recovery_scope['tool_warnings']
        async with activity.step('Preparing your answer'):
            reply = await self.chat.reply(messages, **kwargs)
        if recovery_scope.get('tool_warnings'):
            workflow_logger.set_outcome('degraded', code='OPTIONAL_CAPABILITY_UNAVAILABLE')
        title = history_scope.get('conversation_title') if history_scope else None
        title_fields = dict(conversation_title=title) if title is not None else {}
        warning_fields = dict(tool_warnings=recovery_scope['tool_warnings']) if recovery_scope.get('tool_warnings') else {}
        from app.web_search.citations import web_citations
        web_sources = history_scope.get('web_sources', []) if history_scope else []
        if history_scope and history_scope.get('web_searches'):
            warning_fields.update(web_sources=web_sources, web_citations=web_citations(reply, {source.token for source in web_sources}),
                                  web_searches=history_scope['web_searches'])
        if self.rag is None:
            references = dict(history_references=history_scope['history_references'], memory_references=history_scope['memory_references']) if history_scope else {}
            if history_scope:
                references.update(event_proposals=history_scope.get('event_proposals', []), event_references=history_scope.get('event_references', []), assessment_cards=history_scope.get('assessment_cards', []), interactions=history_scope.get('interactions', []))
            return ChatResponse(role='assistant', content=reply, **warning_fields, **title_fields, **references)
        sources = history_scope.get('study_sources', []) if history_scope else [chunk.source for chunk in result.chunks] if result else []
        if history_scope and history_scope.get('retrieval_status'):
            packet['status'] = history_scope['retrieval_status']
        dynamic_warnings = history_scope.get('retrieval_warnings', []) if history_scope else []
        if dynamic_warnings:
            warning = ' '.join(dict.fromkeys(([warning] if warning else []) + dynamic_warnings))
        valid = {s.token for s in sources}
        cited = list(dict.fromkeys(token for token in re.findall(r'\[\[(S\d+)\]\]', reply) if token in valid))
        # Unknown markers never become links. The UI only resolves the allowlisted tokens.
        return ChatResponse(role='assistant', content=reply, **title_fields, **warning_fields, sources=sources, citations=cited,
                            assessment_cards=history_scope.get('assessment_cards', []) if history_scope else [],
                            interactions=history_scope.get('interactions', []) if history_scope else [],
                            event_proposals=history_scope.get('event_proposals', []) if history_scope else [],
                            event_references=history_scope.get('event_references', []) if history_scope else [],
                            history_references=history_scope['history_references'] if history_scope else [],
                            memory_references=history_scope['memory_references'] if history_scope else [],
                            retrieval_status=packet['status'], retrieval_warning=warning,
                            retrieval_scope=ChatSelection(mode=retrieval.mode if retrieval else 'STANDARD',
                                context_ids=result.context_ids if result else None,
                                document_ids=list(dict.fromkeys(s.document_id for s in sources)),
                                include_archived=retrieval.include_archived if retrieval else False))
