"""Check publisher response headers without relaying remote HTML."""
import asyncio
import re
from typing import Literal
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel

from .images import PublicTransport
from .urls import public_url


class PreviewResult(BaseModel):
    status: Literal['available', 'blocked', 'unavailable']
    url: str | None = None


_checks = asyncio.Semaphore(6)


async def check_preview(url: str, *, transport=None) -> PreviewResult:
    try:
        async with asyncio.timeout(4), _checks, httpx.AsyncClient(
            transport=transport or PublicTransport(), trust_env=False, follow_redirects=False,
        ) as client:
            for _ in range(4):
                url, _ = public_url(url)
                if not url.startswith('https://'):
                    break
                client.cookies.clear()
                async with client.stream('GET', url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers['location'])
                        continue
                    response.raise_for_status()
                    headers = response.headers
                    # Treat publisher-specific ancestor lists conservatively. A
                    # wildcard or absent directive can permit this cross-origin frame.
                    ancestors = re.findall(r'(?:^|[;,])\s*frame-ancestors\s*([^;,]*)',
                                           headers.get('content-security-policy', ''), re.IGNORECASE)
                    if headers.get('x-frame-options') or any('*' not in value.split() for value in ancestors):
                        return PreviewResult(status='blocked')
                    if headers.get('content-type', '').split(';')[0].strip().lower() in ('text/html', 'application/xhtml+xml', 'application/pdf') and not headers.get('content-disposition', '').lower().startswith('attachment'):
                        return PreviewResult(status='available', url=url)
                    break
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, OSError):
        pass
    return PreviewResult(status='unavailable')
