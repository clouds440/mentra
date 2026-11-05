"""Check public publisher pages and return bounded plain text for the reader."""
import asyncio
from contextlib import asynccontextmanager
import re
from typing import Literal
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

from .images import PublicTransport
from .urls import public_url


class PreviewResult(BaseModel):
    status: Literal['available', 'blocked', 'unavailable']
    url: str | None = None


_checks = asyncio.Semaphore(6)
_read_errors = (TimeoutError, httpx.HTTPError, ValueError, KeyError, OSError)


@asynccontextmanager
async def _publisher_response(url, transport=None):
    async with asyncio.timeout(4), _checks, httpx.AsyncClient(
        transport=transport or PublicTransport(), trust_env=False, follow_redirects=False,
    ) as client:
        for _ in range(4):
            url, _ = public_url(url)
            if not url.startswith('https://'):
                break
            client.cookies.clear()
            async with client.stream('GET', url, headers={'Accept-Encoding': 'identity'}) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                yield url, response
                return
    raise ValueError('Publisher redirect limit reached.')


def _media(response):
    return response.headers.get('content-type', '').split(';')[0].strip().lower()


async def check_preview(url: str, *, transport=None) -> PreviewResult:
    try:
        async with _publisher_response(url, transport) as (url, response):
            headers = response.headers
            ancestors = re.findall(r'(?:^|[;,])\s*frame-ancestors\s*([^;,]*)',
                                   headers.get('content-security-policy', ''), re.IGNORECASE)
            if headers.get('x-frame-options') or any('*' not in value.split() for value in ancestors):
                return PreviewResult(status='blocked')
            if _media(response) in ('text/html', 'application/xhtml+xml', 'application/pdf') and not headers.get('content-disposition', '').lower().startswith('attachment'):
                return PreviewResult(status='available', url=url)
    except _read_errors:
        pass
    return PreviewResult(status='unavailable')


async def read_publisher(url: str, *, transport=None):
    limit = 768 * 1024
    try:
        async with _publisher_response(url, transport) as (url, response):
            if _media(response) not in ('text/html', 'application/xhtml+xml', 'text/plain'):
                return None
            if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                return None
            data = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=16384):
                data.extend(chunk[:limit - len(data)])
                if len(data) >= limit:
                    break
            encoding = response.encoding or 'utf-8'
            html = data.decode(encoding, errors='replace')
            plain = _media(response) == 'text/plain'
    except _read_errors + (LookupError,):
        return None
    if plain:
        blocks = [line.strip()[:4000] for line in html[:30000].splitlines() if line.strip()][:100]
        return dict(url=url, blocks=blocks, links=[]) if blocks else None
    return await asyncio.to_thread(_reader_html, url, html)


def _reader_html(url, html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.select('script,style,noscript,iframe,template,nav,aside,footer,form,[hidden],[aria-hidden="true"]'):
        tag.decompose()
    content = soup.select_one('article, main, [role="main"]') or soup.body or soup
    blocks = []
    remaining = 30000
    for tag in content.select('h1,h2,h3,h4,p,li,blockquote,pre')[:150]:
        line = ' '.join(tag.get_text().split())
        if not line or line in blocks:
            continue
        blocks.append(line[:min(4000, remaining)])
        remaining -= len(blocks[-1])
        if remaining <= 0:
            break
    if not blocks:
        fallback = ' '.join(content.get_text(' ', strip=True).split())[:4000]
        if not fallback:
            return None
        blocks.append(fallback)
    links = {}
    for anchor in content.select('a[href]')[:100]:
        title = ' '.join(anchor.get_text(' ', strip=True).split())[:300]
        if not title:
            continue
        try:
            href, _ = public_url(urljoin(url, anchor['href']))
        except ValueError:
            continue
        if href.startswith('https://') and href != url:
            links.setdefault(href, title)
        if len(links) >= 24:
            break
    return dict(url=url, blocks=blocks, links=[dict(url=href, title=title) for href, title in links.items()])
