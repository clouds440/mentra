"""Validated first-turn model output and the provisional title fallback."""
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class NewChatReply(BaseModel):
    """Return the final learner-facing answer and a short conversation title."""
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1, description='Complete answer to the learner, with no title prefix.')
    conversation_title: str = Field(min_length=1, max_length=80,
        description='Concise descriptive title in the learner language, usually 3-7 words; no markdown or quotes.')

    @field_validator('conversation_title', mode='before')
    @classmethod
    def normalize_title(cls, value):
        return ' '.join(value.split()) if isinstance(value, str) else value


def provisional_title(content):
    first = next((line.strip() for line in content.splitlines() if line.strip()), 'New chat')
    return ('Code discussion' if first.startswith(('```', '~~~')) else
            re.sub(r'^#{1,6}\s+|\*\*|__|`', '', first)[:80]) or 'New chat'
