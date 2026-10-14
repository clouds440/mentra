"""Authenticated research, separate from the keyless search transport."""
import json
import httpx
from .provider import ProviderError
from .schemas import SearchInput

ENDPOINT = 'https://api.you.com/v1/research'


class YouResearchProvider:
    namespace = 'research'
    timeout = 45

    def __init__(self, api_key: str, *, transport=None):
        self._api_key = api_key
        self._transport = transport
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=False,
            trust_env=False, transport=transport)

    async def search(self, request: SearchInput):
        if not self._api_key or self._client.is_closed:
            raise ProviderError('disabled')
        body = dict(input=request.query, research_effort='standard')
        if request.website:
            body['source_control'] = dict(include_domains=[request.website])
        try:
            async with self._client.stream('POST', ENDPOINT, headers={'X-API-Key': self._api_key}, json=body) as response:
                if response.status_code == 429:
                    raise ProviderError('rate_limited')
                if response.status_code == 402:
                    raise ProviderError('quota_exhausted')
                if response.status_code != 200:
                    raise ProviderError()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 512 * 1024:
                        raise ProviderError()
            output = json.loads(data)['output']
            report, sources = output['content'], output['sources']
            if not isinstance(report, str) or not isinstance(sources, list):
                raise ProviderError()
            return dict(research_report=report, results=dict(web=sources, news=[]))
        except httpx.TimeoutException:
            raise ProviderError('timeout') from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ProviderError() from None

    async def close(self):
        await self._client.aclose()
