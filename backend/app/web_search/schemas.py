"""Dated provider-independent search contracts."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .urls import normalize_host, normalize_query


class SearchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=400)
    website: str | None = Field(default=None, max_length=2048)

    @field_validator('query')
    @classmethod
    def clean_query(cls, value):
        value = ' '.join(value.split())
        if not value or len(value.split()) > 50:
            raise ValueError('Search needs 1 to 50 words and at most 400 characters.')
        return value

    @model_validator(mode='after')
    def scope_query(self):
        self.website = normalize_host(self.website) if self.website else None
        self.query, self.website = normalize_query(self.query, self.website)
        return self


class WebSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(default='', pattern=r'^(W[1-9]\d?)?$')
    url: str = Field(max_length=2048)
    domain: str = Field(max_length=253)
    favicon_url: str = Field(max_length=2048)
    title: str = Field(max_length=200)
    excerpt: str = Field(max_length=1200)
    searched_at: datetime
    published_date: date | None = None
    published_at: datetime | None = None
    updated_date: date | None = None
    updated_at: datetime | None = None
    data_as_of: str | None = Field(default=None, max_length=100)
    provider_fetched_at: datetime | None = None
    date_raw: str | None = Field(default=None, max_length=100)
    date_precision: Literal['date', 'datetime', 'unknown'] = 'unknown'
    date_origin: Literal['provider_reported', 'unavailable'] = 'unavailable'
    source_date_status: Literal['available', 'missing', 'invalid', 'future'] = 'missing'
    warnings: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def valid_links(self):
        from .urls import public_url, favicon_url
        url, host = public_url(self.url)
        if url != self.url or host != self.domain or self.favicon_url != favicon_url(host):
            raise ValueError('Source links must use the validated public origin.')
        return self


class SearchResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome: Literal['ok', 'partial', 'no_results', 'unavailable', 'quota_exhausted', 'rate_limited', 'timeout', 'invalid_input', 'budget_exhausted', 'disabled']
    reason: str | None = Field(default=None, max_length=240)
    current_date: date
    current_datetime: datetime
    reference_timezone: str
    delivered_at: datetime
    searched_at: datetime | None = None
    reused_within_turn: bool = False
    cache_hit: bool = False
    cache_expires_at: datetime | None = None
    website: str | None = None
    research_report: str | None = Field(default=None, max_length=6000)
    details_omitted: bool = False
    sources: list[WebSource] = Field(default_factory=list, max_length=5)
