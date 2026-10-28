from pydantic import ValidationError
from app.core.exceptions import AppError
from .schemas import EventDraft


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class EventProposalService:
    def __init__(self, repository, events, graph, llm=None):
        self.repository, self.events, self.graph = repository, events, graph
        self.llm=llm

    def create(self, owner, body, scope):
        result = self.repository.create(owner, body, scope)
        return self._prepare_result(owner, result)

    def _prepare_result(self, owner, result):
        if result.get('outcome') == 'awaiting_confirmation':
            identifier = result['proposal']['id']
            self.graph.prepare(owner, identifier)
            latest = self.repository.reconcile_review(owner, identifier)
            if latest is None:
                return dict(outcome='already_known', reason='This event review is no longer available.')
            result = dict(result, proposal=latest.model_dump(mode='json'),
                          outcome='awaiting_confirmation' if latest.state in ('pending', 'deciding') else 'already_known')
        return result

    async def admit(self, owner, body, scope, *, capture_admission=None):
        from starlette.concurrency import run_in_threadpool
        from .proposals import EventAdmission, ProposalDecision
        from app.langchain.prompts import PromptSource
        source=next((row for row in scope.get('context_rows',[]) if row['id']==str(body.message_id) and row['role']=='user'),None)
        if not source or body.quote not in source['content']:
            raise AppError('PROPOSAL_EVIDENCE_INVALID','Use an exact visible user statement.',422)
        from .capture import normalize_candidate
        body = body.model_copy(update={'candidate': normalize_candidate(body.candidate)})
        supported=False
        if self.llm is not None or capture_admission is not None:
            preferences=await run_in_threadpool(self.events.preferences,owner)
            try:
                admission=capture_admission or await self.llm.ainvoke(PromptSource.EVENT_ADMISSION,dict(user_statement=source['content'],quote=body.quote,
                    occurred_at=source['created_at'].isoformat(),account_timezone=preferences['timezone'] or source.get('metadata',{}).get('timezone'),candidate=body.model_dump(mode='json')),output_schema=EventAdmission)
                if not admission.supported or not admission.first_party or not admission.actual_event:
                    return dict(outcome='rejected',reason='This statement does not support a personal event.')
                supported=admission.complete_unambiguous and admission.timezone_supported and admission.confidence>=.95
            except Exception as error:
                from app.langchain.tool_execution import LIFECYCLE_CODES
                if isinstance(error, AppError) and error.code in LIFECYCLE_CODES:
                    raise
                supported=False
        result=await run_in_threadpool(self.repository.create,owner,body,scope)
        if supported and body.action=='create' and result['outcome']=='awaiting_confirmation':
            proposal=result['proposal']
            try:
                details=EventDraft.model_validate(body.candidate.model_dump())
                self.events._context(owner,details)
                claim=await run_in_threadpool(self.repository.claim,owner,proposal['id'],ProposalDecision(expected_revision=proposal['revision'],decision='approve',details=details))
                if not claim['terminal']:
                    approved=await run_in_threadpool(self.repository.commit,owner,proposal['id'],claim['claim_id'],automatic=True)
                else:approved=claim['proposal']
                event=await run_in_threadpool(self.events.detail,owner,str(approved.event_id))
                return dict(outcome='saved',event=event)
            except (ValidationError,AppError) as error:
                from app.langchain.tool_execution import LIFECYCLE_CODES
                if isinstance(error, AppError) and (error.code in LIFECYCLE_CODES or error.status_code >= 500):
                    raise
                # A failed automatic gate leaves a reviewable domain proposal.
                await run_in_threadpool(self.repository.release,owner,proposal['id'])
                latest=await run_in_threadpool(self.repository.detail,owner,proposal['id'])
                return await run_in_threadpool(self._prepare_result, owner, dict(outcome='awaiting_confirmation', proposal=latest.model_dump(mode='json')))
        return await run_in_threadpool(self._prepare_result, owner, result)

    def list(self, owner, conversation_id=None): return self.repository.list(owner, conversation_id)
    def detail(self, owner, identifier): return self.repository.detail(owner, identifier)

    def decide(self, owner, identifier, body):
        proposal = self.repository.detail(owner, identifier)
        if body.decision == 'approve' and proposal.action in ('create', 'edit'):
            try: details = body.details or EventDraft.model_validate(proposal.candidate.model_dump())
            except ValidationError:
                raise AppError('PROPOSAL_DETAILS_REQUIRED', 'Review the date, time and timezone before adding this event.', 422) from None
            self.events._context(owner, details)
        claim = self.repository.claim(owner, identifier, body)
        if claim['terminal']: return claim['proposal']
        self.graph.decide(owner, identifier, claim['decision']['decision'])
        return self.repository.commit(owner, identifier, claim['claim_id'])


@workflow_logger.operation(outcome='success')
def create_event_proposals(sessions, events, llm=None):
    from app.history_management.repositories.events.proposals import EventProposalRepository
    from app.langchain.graphs.event_confirmation import EventConfirmationGraph
    return EventProposalService(EventProposalRepository(sessions, events.repository), events,
        EventConfirmationGraph(sessions.kw['bind']),llm)
