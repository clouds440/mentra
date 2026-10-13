"""Cheap candidate detection only; semantic admission decides actual personal events."""
import re
from pydantic import Field
from .schemas import Contract
from .proposals import EventCandidate, EventAdmission


def event_candidate(text):
    # Subjects and event kinds are intentionally unrestricted. This is only a
    # temporal/agenda hint, never authorization or a semantic yes/no decision.
    temporal = bool(re.search(r'\b(tomorrow|tonight|today|next (?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|upcoming|due|deadline|scheduled|monday|tuesday|wednesday|thursday|friday|saturday|sunday|at \d|\d\s*(?:am|pm))\b|\b\d{4}-\d{2}-\d{2}\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d', text, re.I))
    first_party = bool(re.search(r'\b(I|my|our|we|me)\b', text, re.I))
    activity = bool(re.search(r'\b(assessment|assignment|quiz|test|exam|project|presentation|meeting|appointment|seminar|workshop|deadline|event|remind)\b', text, re.I))
    return temporal and (first_party or activity) or first_party and activity


def practice_request(text):
    return bool(re.search(r'\b(?:quiz|test) me\b|\b(?:give|generate|create|make|build|want|need)\b.*\b(?:practice|interactive|assessment|questions?|quiz|test|mock)\b|\b(?:practice|assess me)\b', text, re.I))


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
