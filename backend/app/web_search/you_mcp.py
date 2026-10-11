"""Official SDK Streamable HTTP client, fixed keyless search-only endpoint."""
import asyncio
import json
from time import monotonic
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp import types
from .provider import ProviderError
from .schemas import SearchInput

ENDPOINT = 'https://api.you.com/mcp?profile=free&tools=you-search'
MAX_RESPONSE_BYTES = 512 * 1024


class LimitedStream(httpx2.AsyncByteStream):
    def __init__(self, response, transport):
        self.response, self.transport = response, transport

    async def __aiter__(self):
        async for chunk in self.response.aiter_bytes():
            self.transport.received += len(chunk)
            if self.transport.received > MAX_RESPONSE_BYTES:
                raise ProviderError()
            yield chunk

    async def aclose(self):
        await self.response.aclose()


class BoundedTransport(httpx2.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx2.AsyncHTTPTransport(retries=0)
        self.received = 0

    async def handle_async_request(self, request):
        if request.url.host != 'api.you.com' or request.url.scheme != 'https' or request.url.path != '/mcp':
            raise ProviderError()
        # Do not acquire or forward credentials/cookies even if a remote session requests them.
        for name in ('authorization', 'cookie', 'payment-signature', 'x-payment'):
            request.headers.pop(name, None)
        request.headers['Accept-Encoding'] = 'identity'
        response = await self.inner.handle_async_request(request)
        if response.status_code == 429:
            await response.aclose()
            raise ProviderError('rate_limited')
        if response.status_code >= 300:
            await response.aclose()
            raise ProviderError()
        headers = [(key, value) for key, value in response.headers.multi_items() if key.lower() not in ('content-encoding', 'content-length')]
        return httpx2.Response(response.status_code, headers=headers, stream=LimitedStream(response, self))

    async def aclose(self):
        await self.inner.aclose()


def result_payload(result):
    if result.is_error:
        raise ProviderError()
    structured = getattr(result, 'structured_content', None)
    if isinstance(structured, dict):
        payload = structured
    else:
        blocks = [block.text for block in result.content if getattr(block, 'type', None) == 'text']
        if len(blocks) != 1 or len(blocks[0].encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise ProviderError()
        try:
            payload = json.loads(blocks[0])
        except (ValueError, TypeError) as error:
            raise ProviderError() from error
    if not isinstance(payload, dict) or len(json.dumps(payload).encode('utf-8')) > MAX_RESPONSE_BYTES:
        raise ProviderError()
    return payload


class YouMCPProvider:
    def __init__(self):
        self.protocol = None
        self.contract_until = 0.0
        self.failures = 0
        self.cooldown_until = 0.0
        self._contract_lock = asyncio.Lock()

    async def search(self, request: SearchInput):
        if monotonic() < self.cooldown_until:
            raise ProviderError()
        try:
            # SDK context managers enter and leave in this same task. No background session sharing.
            async with httpx2.AsyncClient(transport=BoundedTransport(), timeout=20, follow_redirects=False, trust_env=False) as client:
                async with streamable_http_client(ENDPOINT, http_client=client, max_sse_event_size=MAX_RESPONSE_BYTES) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        initialized = await session.initialize()
                        self.protocol = initialized.protocol_version
                        async with self._contract_lock:
                            if monotonic() >= self.contract_until:
                                listed = await session.list_tools()
                                search = next((tool for tool in listed.tools if tool.name == 'you-search'), None)
                                if search is None or search.input_schema.get('properties', {}).get('query', {}).get('type') != 'string':
                                    raise ProviderError()
                                if len(json.dumps(search.model_dump(mode='json')).encode('utf-8')) > 65536:
                                    raise ProviderError()
                                self.contract_until = monotonic() + 3600
                        # Snippets-only is available in the free search contract; no paid extraction.
                        overrides = dict(count=5, extraction='none', safesearch='moderate')
                        if request.website:
                            overrides['include_domains'] = [request.website]
                        result = await session.call_tool('you-search', dict(query=request.query, count=5, extraction='none', safesearch='moderate'),
                            meta=types.RequestParamsMeta(**{'com.you.com/search': overrides}))
                        payload = result_payload(result)
                        self.failures = 0
                        return payload
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # SDK task groups wrap transport failures. Keep raw payloads/exceptions out of public results/logs.
            def outcome(exc):
                if isinstance(exc, ProviderError):
                    return exc.outcome
                if isinstance(exc, (TimeoutError, httpx2.TimeoutException)):
                    return 'timeout'
                for nested in getattr(exc, 'exceptions', ()):
                    found = outcome(nested)
                    if found != 'unavailable':
                        return found
                return 'unavailable'
            status = outcome(error)
            if status != 'rate_limited':
                self.failures += 1
                if self.failures >= 3:
                    self.cooldown_until = monotonic() + 60
                    self.contract_until = 0
            raise ProviderError(status) from None

    async def close(self):
        # HTTP resources belong to individual search contexts and close on cancellation.
        pass
