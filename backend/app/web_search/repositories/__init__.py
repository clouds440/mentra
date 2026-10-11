"""Persistence failures exposed without leaking database implementation details."""
from datetime import datetime
from typing import Mapping, Protocol


class RepositoryError(RuntimeError):
    pass


class UsageStore(Protocol):
    def reserve(self, owner: str, operation: str, now: datetime) -> str: ...
    def mark(self, operation: str, state: str) -> None: ...
    def cached(self, owner: str, key: str, now: datetime) -> Mapping | None: ...
    def cache_result(self, owner: str, key: str, now: datetime, expires: datetime, payload: dict) -> None: ...
