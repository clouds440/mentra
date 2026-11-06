"""Recognize the exact, explicit difficulty action emitted by the chat card."""
import re
from uuid import UUID

_DIFFICULTY_ACTION = re.compile(
    r'Make (chat draft|assessment) ([0-9a-fA-F-]{36}) (easier|harder)\. '
    r'Keep the topic, question count and delivery, and preserve the original\.')


def difficulty_action(text, *, draft_id=None, assessment_id=None):
    match = _DIFFICULTY_ACTION.fullmatch(text)
    if not match:
        return None
    kind, identifier, direction = match.groups()
    try:
        target = draft_id if kind == 'chat draft' else assessment_id
        if target is None or UUID(identifier) != UUID(target):
            return None
    except (ValueError, TypeError, AttributeError):
        return None
    return direction
