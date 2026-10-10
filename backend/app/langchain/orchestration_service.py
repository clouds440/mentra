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
    def __init__(self, chat, *, rag=None, learner=None, history=None, attachments=None, event_proposals=None, assessments=None):
        self.chat, self.rag, self.learner, self.history = chat, rag, learner, history
        self.attachments = attachments
        self.event_proposals = event_proposals
        self.assessments = assessments

    async def generate_assessment(self, owner, request):
        if self.assessments is None: raise AppError('ASSESSMENT_UNAVAILABLE', 'Assessments are unavailable.', 503)
        return await self.assessments.generate(owner, request)

    async def chat_reply(self, messages, retrieval, owner, history_policy=None, history_scope=None):
        activity = history_scope.get('activity', ActivityPublisher()) if history_scope else ActivityPublisher()
        query = next((content for role, content in reversed(messages) if role == 'user'), '')
        from .planning import plan_request
        plan = plan_request(query, attachments=bool(history_scope and history_scope.get('attachment_ids')),
                            selected_sources=bool(retrieval and (retrieval.document_ids or retrieval.context_ids)))
        modules = {step.module for step in plan.steps}
        await activity.emit('planning', 'completed', 'Your request is ready to process')
        result, warning = None, None
        if self.rag is not None and 'rag' in modules:
            selection = retrieval.model_dump() if retrieval else {}
            try:
                async with activity.step('Reading documents'):
                    result = await run_in_threadpool(self.rag.search, owner, SearchRequest(query=query, **selection))
            except AppError as exc:
                if exc.code != 'RAG_UNAVAILABLE':
                    raise
                warning = exc.message
                workflow_logger.set_outcome('degraded', code='RAG_UNAVAILABLE')
        packet = dict(status=result.status if result else 'unavailable' if warning else 'no_eligible_sources',
                      sources=[chunk.source.model_dump() for chunk in result.chunks] if result else [])
        if result and result.warnings:
            workflow_logger.set_outcome('degraded', code='RETRIEVAL_DEGRADED')
            warning = ' '.join(result.warnings)
        kwargs = {'source_packet': packet} if self.rag is not None else {}
        if self.attachments is not None and history_scope:
            ids = history_scope.get('attachment_ids', [])
            if not ids:
                # Follow-up questions can refer to the latest attached user message.
                for row in reversed(history_scope['context_rows']):
                    if row.get('metadata', {}).get('attachments'):
                        ids = [item['id'] for item in row['metadata']['attachments']][:4]
                        break
            documents = []
            for identifier in ids:
                async with activity.step('Reading documents and extracting image text'):
                    extracted = await run_in_threadpool(self.attachments.extract, owner, identifier, history_scope['conversation_id'])
                    documents.append(self.attachments.context(extracted, query, maximum=8000 // max(1, len(ids))))
            if documents:
                kwargs['document_context'] = documents
        if self.history is not None and self.history.profile is not None and 'profile' in modules:
            async with activity.step('Checking your learning preferences'):
                kwargs['profile_context'] = await run_in_threadpool(self.history.profile.prompt_context, owner)
                if kwargs['profile_context'] is not None:
                    kwargs['profile_context'] = kwargs['profile_context'].model_dump(mode='json')
        if self.learner is not None and owner and 'learner' in modules:
            async with activity.step('Checking your learning context'):
                kwargs['learner_context'] = await run_in_threadpool(self.learner.get_relevant_context, LearnerContextRequest(learner_id=owner, query=query[:4000], context_ids=retrieval.context_ids if retrieval else None))
        policy = history_policy or HistoryContextPolicy()
        if history_scope is not None and self.history is not None:
            history_scope['activity'] = activity
            history_scope['learner_service'] = self.learner
            history_scope['event_proposal_service'] = self.event_proposals
            async def delta(value):
                await activity.emit('response-stream', 'running', 'Writing your response', token_delta=value, token_reset=value is None)
            history_scope['on_delta'] = delta
            history_scope['history_token_budget'] = policy.max_tokens
            kwargs['history_runtime'] = (self.history, owner, history_scope)
        else:
            system_text = get_system_prompt(PromptSource.CHAT)
            if self.rag is not None:
                system_text += '\n\n' + get_system_prompt(PromptSource.RAG_CONTEXT) + '\n\n' + json.dumps({'study_sources': packet}, ensure_ascii=False)
            if kwargs.get('learner_context') is not None:
                system_text += '\n' + kwargs['learner_context'].model_dump_json()
            if kwargs.get('document_context'):
                system_text += '\n' + json.dumps(kwargs['document_context'])
            messages = policy.for_prompt(messages, system_text)
        async with activity.step('Preparing your answer'):
            reply = await self.chat.reply(messages, **kwargs)
        if self.rag is None:
            references = dict(history_references=history_scope['history_references'], memory_references=history_scope['memory_references']) if history_scope else {}
            if history_scope:
                references.update(event_proposals=history_scope.get('event_proposals', []), event_references=history_scope.get('event_references', []))
            return ChatResponse(role='assistant', content=reply, **references)
        sources = [chunk.source for chunk in result.chunks] if result else []
        valid = {s.token for s in sources}
        cited = list(dict.fromkeys(token for token in re.findall(r'\[\[(S\d+)\]\]', reply) if token in valid))
        # Unknown markers never become links. The UI only resolves the allowlisted tokens.
        return ChatResponse(role='assistant', content=reply, sources=sources, citations=cited,
                            event_proposals=history_scope.get('event_proposals', []) if history_scope else [],
                            event_references=history_scope.get('event_references', []) if history_scope else [],
                            history_references=history_scope['history_references'] if history_scope else [],
                            memory_references=history_scope['memory_references'] if history_scope else [],
                            retrieval_status=packet['status'], retrieval_warning=warning,
                            retrieval_scope=ChatSelection(mode=retrieval.mode if retrieval else 'STANDARD',
                                context_ids=result.context_ids if result else None,
                                document_ids=list(dict.fromkeys(s.document_id for s in sources)),
                                include_archived=retrieval.include_archived if retrieval else False))
