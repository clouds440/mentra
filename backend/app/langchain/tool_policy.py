"""Small, explicit capability metadata shared by selection and discovery."""
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from app.chat.titles import NewChatReply


from .capabilities import DOMAINS, WRITES, OUTCOMES as CAPABILITIES, catalog

__all__ = ['DOMAINS', 'WRITES', 'CAPABILITIES', 'catalog', 'is_write', 'DirectAnswer',
           'DirectNewChatReply', 'approved_direct']


def is_write(name, arguments):
    return name in WRITES or (name == 'user_memory' and arguments.get('action') != 'recall')


class DirectAnswer(BaseModel):
    """Final answer only when every part is general and needs no tools."""
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1)
    general_query: StrictBool
    needs_tools: StrictBool
    uncertain: StrictBool


class DirectNewChatReply(NewChatReply):
    """First-turn answer/title plus explicit no-tool eligibility, in one call."""
    general_query: StrictBool
    needs_tools: StrictBool
    uncertain: StrictBool


def approved_direct(response):
    return response.general_query is True and response.needs_tools is False and response.uncertain is False
