"""Canonical UUID identifiers without persistence or authentication dependencies."""

from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator


def canonical_learner_id(value) -> str:
    if not isinstance(value, (str, UUID)):
        raise ValueError('learner_id must be a UUID')
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('learner_id must be a UUID') from exc


LearnerId = Annotated[str, BeforeValidator(canonical_learner_id)]
