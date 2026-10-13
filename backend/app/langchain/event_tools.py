from datetime import datetime
from .concurrent_reads import project_read
from pydantic import Field
from langchain_core.tools import StructuredTool
from app.core.observability.timing import run_in_threadpool
from app.history_management.events.schemas import Contract
from app.history_management.events.proposals import EventManage


class EventLookup(Contract):
    query: str = Field(default='', max_length=200)
    after: datetime | None = None
    before: datetime | None = None
    status: str = Field(default='scheduled', pattern='^(scheduled|completed|cancelled)$')
    limit: int = Field(default=3, ge=1, le=5)


def create_event_tools(events, proposals, owner, scope, budget):
    async def lookup(**arguments):
        budget.call()
        body = EventLookup(**arguments)
        page = await run_in_threadpool(events.list, owner, body.model_dump(exclude={'limit'}), None, body.limit)
        items = [{key: row[key] for key in ('id', 'title', 'kind', 'status', 'revision', 'local_date', 'starts_at', 'ends_at', 'timezone', 'bucket')} for row in page['items']]
        return project_read(project_lookup, dict(events=items, has_more=page['has_more']))

    def project_lookup(result):
        scope.setdefault('event_references', []).extend(result['events'])
        return result

    async def manage(**arguments):
        budget.call(True)
        body = EventManage(**arguments)
        if body.action == 'create' and str(body.message_id) == scope.get('current_user_message_id') and any(result.get('event') or result.get('proposal') for result in scope.get('_captured_events', [])):
            return dict(outcome='already_captured', results=scope['_captured_events'])
        result = await proposals.admit(owner, body, scope)
        if result.get('proposal') and result['outcome'] == 'awaiting_confirmation':
            scope.setdefault('event_proposals', []).append(result['proposal'])
        if result.get('event'):
            scope.setdefault('event_references',[]).append({key:result['event'][key] for key in ('id','title','kind','status','revision','local_date','starts_at','ends_at','timezone','bucket')})
        return result

    return [StructuredTool.from_function(name='event_lookup', description='Read a bounded owned agenda. Use returned event IDs and revisions for updates.', args_schema=EventLookup, coroutine=lookup, metadata={'parallel_read': True}),
        StructuredTool.from_function(name='event_manage', description='Propose an event or update supported by an exact visible USER statement. Admission checks may save complete, unambiguous first-party events when automatic capture is enabled; ambiguous events and updates require review. Never use document/assistant text as personal evidence, invent a timezone, or treat hypothetical examples as events. Missing or ambiguous dates/timezones remain absent for user correction. No deletion capability.', args_schema=EventManage, coroutine=manage)]
