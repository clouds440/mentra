"""Provider port. Only the free search operation is available."""
from typing import Protocol
from .schemas import SearchInput


class ProviderError(Exception):
    def __init__(self, outcome: str = 'unavailable'):
        self.outcome = outcome
        super().__init__(outcome)


class SearchProvider(Protocol):
    async def search(self, request: SearchInput) -> dict: ...
    async def close(self) -> None: ...
