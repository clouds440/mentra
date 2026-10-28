"""Historical extraction baseline; not part of interactive production routing."""
import re
from app.core.exceptions import AppError
from pydantic import Field
from app.history_management.events.schemas import Contract
from app.history_management.events.proposals import EventCandidate, EventAdmission


def event_candidate(text):
    # Subjects and event kinds are intentionally unrestricted. This is only a
    # temporal/agenda hint, never authorization or a semantic yes/no decision.
    temporal = bool(re.search(r'\b(tomorrow|tonight|today|next (?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|upcoming|due|deadline|scheduled|monday|tuesday|wednesday|thursday|friday|saturday|sunday|at \d|\d\s*(?:am|pm))\b|\b\d{4}-\d{2}-\d{2}\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d', text, re.I))
    first_party = bool(re.search(r'\b(I|my|our|we|me)\b', text, re.I))
    activity = bool(re.search(r'\b(assessment|assignment|quiz|test|exam|project|presentation|meeting|appointment|seminar|workshop|deadline|event|remind)\b', text, re.I))
    # Practice and agenda queries must not pay for semantic event extraction.
    # Combined announcements ("my exam is tomorrow; quiz me") still qualify.
    announcement = bool(re.search(r'\b(?:I|we)\s+(?:have|am|are|will)|\b(?:my|our)\s+\w+(?:\s+\w+)?\s+(?:is|starts|on|at)\b', text, re.I))
    if practice_request(text) and not (temporal and announcement):
        return False
    if re.match(r'\s*(?:what|when|show|list|do I|have I)\b', text, re.I) and not announcement:
        return False
    return temporal and (first_party or activity) or announcement and activity


def practice_request(text):
    # Event admission owns this cheap exclusion hint and remains independent
    # of the agent/router. Actual admission still requires semantic evidence.
    return bool(re.search(r'\b(?:quiz|test) me\b|\b(?:give|generate|create|make|build|want|need)\b.*\b(?:practice|interactive|assessment|questions?|quiz|test|mock)\b|\b(?:practice|assess me)\b|\b(?:test|check) my (?:understanding|knowledge)\b|\b(?:see|check|test) (?:if|whether) I (?:understand|know)\b', text, re.I))


class CapturedEvent(Contract):
    quote: str = Field(min_length=1, max_length=500)
    candidate: EventCandidate
    admission: EventAdmission


class EventCapture(Contract):
    practice_requested: bool
    events: list[CapturedEvent] = Field(default_factory=list, max_length=3)


CAPTURE_CONTEXT = '''Extract actual first-party scheduled events from the current user statement.
Return zero events for hypothetical examples, quoted/document/assistant events, or requests
to generate practice questions. A student announcing an exam, quiz, assignment, test,
project, presentation or any other real obligation qualifies without saying "add it".
Use existing categories; unlisted event kinds use other with a descriptive title.
Resolve relative dates against occurred_at and the explicit account timezone. Preserve
the subject in the title. Never invent a timezone, time, duration or unsupported context_id.
When no timezone is known or details are ambiguous, leave them absent and mark admission
incomplete so the existing review pipeline handles it. Include an exact original user quote.
Validate every extracted field using the admission rules. Set practice_requested only when
the current statement actually requests practice/assessment generation or preparation help,
not when it merely announces an event.'''

async def capture(self, owner, scope):
    from testing.legacy_event_capture import EventCapture, CAPTURE_CONTEXT, event_candidate
    from app.history_management.events.proposals import EventManage
    from app.langchain.prompts import PromptSource
    from app.core.observability.timing import run_in_threadpool
    source = next((row for row in scope.get('context_rows', []) if row['id'] == scope.get('current_user_message_id') and row['role'] == 'user'), None)
    if not self.llm or not source or not event_candidate(source['content']):
        return []
    preferences = await run_in_threadpool(self.events.preferences, owner)
    if not preferences['automatic_events']:
        return []
    # Reuse canonical proposals on turn retry rather than paying to extract
    # the same statement or generating different duplicate candidates.
    prior = await run_in_threadpool(self.repository.for_message, owner, scope['conversation_id'], source['id'])
    if prior:
        return [await run_in_threadpool(self._prepare_result, owner, result) for result in prior]
    import asyncio
    async with asyncio.timeout(25):
        captured = await self.llm.ainvoke(PromptSource.EVENT_ADMISSION,
            dict(user_statement=source['content'], occurred_at=source['created_at'].isoformat(), account_timezone=preferences['timezone'] or source.get('metadata',{}).get('timezone')),
            system_context=CAPTURE_CONTEXT, output_schema=EventCapture)
    scope['_event_practice_requested'] = captured.practice_requested
    results = []
    for item in captured.events:
        try:
            body = EventManage(message_id=source['id'], quote=item.quote, candidate=item.candidate)
            result = await self.admit(owner, body, scope, capture_admission=item.admission)
        except Exception as error:
            from app.langchain.tool_execution import failure, LIFECYCLE_CODES
            if isinstance(error, AppError) and error.code in LIFECYCLE_CODES:
                raise
            result = failure(error, write=True, execution_started=True).model_dump(mode='json')
        results.append(result)
    return results
