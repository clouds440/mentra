from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.web_search.urls import public_url

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Resource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class WebResource(Resource):
    kind: Literal['web']
    url: str = Field(max_length=2048)

    @field_validator('url')
    @classmethod
    def validate_url(cls, value):
        from urllib.parse import urlsplit, urlunsplit
        normalized, _ = public_url(value)
        if not normalized.startswith('https://'):
            raise ValueError('Use a public HTTPS source.')
        return urlunsplit((*urlsplit(normalized)[:4], urlsplit(value).fragment))


class LibraryResource(Resource):
    kind: Literal['library']
    document_id: Identifier
    version_id: Identifier | None = None
    generation_id: Identifier | None = None
    chunk_id: Identifier | None = None


class AttachmentResource(Resource):
    kind: Literal['attachment']
    conversation_id: UUID
    file_id: UUID


class HistoryResource(Resource):
    kind: Literal['history']
    conversation_id: UUID
    sequence: int = Field(ge=1, le=2147483647)


class MemoryResource(Resource):
    kind: Literal['memory']
    memory_id: UUID
    revision: int = Field(ge=1, le=2147483647)


PanelResource = Annotated[WebResource | LibraryResource | AttachmentResource | HistoryResource | MemoryResource,
                          Field(discriminator='kind')]


class ChatExcerptSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['chat']
    title: Literal['Mentra response', 'Your message']


class SourceAnnotation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: PanelResource | ChatExcerptSource
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)]
