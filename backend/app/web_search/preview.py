"""Check public publisher pages and return bounded plain text for the reader."""
import asyncio
from contextlib import asynccontextmanager
import re
import zlib
from dataclasses import dataclass
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
async def _publisher_response(url, transport=None, *, timeout=4):
    async with asyncio.timeout(timeout), _checks, httpx.AsyncClient(
        transport=transport or PublicTransport(), trust_env=False, follow_redirects=False,
    ) as client:
        for _ in range(4):
            url, _ = public_url(url)
            if not url.startswith('https://'):
                break
            client.cookies.clear()
            async with client.stream('GET', url, headers={'Accept-Encoding': 'gzip, deflate',
                    'Accept': 'text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1',
                    'User-Agent': 'Mentra/1.0 (public-source reader)'}) as response:
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


@dataclass(frozen=True)
class PublisherRead:
    status: str
    code: str | None = None
    page: dict | None = None
    http_status: int | None = None
    truncated: bool = False


async def read_publisher_result(url: str, *, transport=None):
    limit = 768 * 1024
    truncated = False
    try:
        async with _publisher_response(url, transport, timeout=6) as (url, response):
            if _media(response) not in ('text/html', 'application/xhtml+xml', 'text/plain'):
                return PublisherRead('unsupported', 'PUBLISHER_UNSUPPORTED_CONTENT')
            coding = response.headers.get('content-encoding', 'identity').strip().lower()
            if coding not in ('identity', 'gzip', 'deflate'):
                return PublisherRead('unsupported', 'PUBLISHER_UNSUPPORTED_ENCODING')
            # In-memory/test transports may supply an already decoded response.
            preloaded = response.is_stream_consumed
            decoder = zlib.decompressobj(31 if coding == 'gzip' else 15) if coding != 'identity' and not preloaded else None
            data = bytearray()
            received = 0
            async def chunks():
                if preloaded:
                    yield response.content[:limit+1]
                else:
                    async for chunk in response.aiter_raw(chunk_size=16384):
                        yield chunk
            # Bound encoded and decoded bytes independently. A compressed bomb
            # must never allocate the unbounded decoded publisher response.
            async for chunk in chunks():
                encoded_remaining = max(0, limit-received)
                received += len(chunk)
                remaining = limit - len(data)
                decoded = decoder.decompress(chunk[:encoded_remaining], remaining) if decoder else chunk[:remaining]
                data.extend(decoded)
                if len(data) >= limit or received > limit:
                    truncated = True
                    break
            if decoder and not truncated and not decoder.eof:
                return PublisherRead('unavailable', 'PUBLISHER_INVALID_ENCODING')
            encoding = response.encoding or 'utf-8'
            html = data.decode(encoding, errors='replace')
            plain = _media(response) == 'text/plain'
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        category = 'blocked' if status in (401,403) else 'rate_limited' if status == 429 else 'not_found' if status in (404,410) else 'unavailable'
        return PublisherRead(category, 'PUBLISHER_HTTP_' + str(status), http_status=status)
    except (TimeoutError, httpx.TimeoutException):
        return PublisherRead('timeout', 'PUBLISHER_TIMEOUT')
    except _read_errors + (LookupError, zlib.error):
        return PublisherRead('unavailable', 'PUBLISHER_READ_FAILED')
    if plain:
        blocks = [line.strip()[:4000] for line in html[:30000].splitlines() if line.strip()][:100]
        page = dict(url=url, blocks=blocks, links=[]) if blocks else None
    else:
        page = await asyncio.to_thread(_reader_html, url, html)
    return PublisherRead('ok', page=page, truncated=truncated) if page else PublisherRead('empty', 'PUBLISHER_NO_READABLE_TEXT')


async def read_publisher(url: str, *, transport=None):
    """Public Reader endpoint keeps its page-or-null presentation contract."""
    return (await read_publisher_result(url, transport=transport)).page


def _reader_html(url, html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.select('script,style,noscript,iframe,template,nav,aside,footer,form,[hidden],[aria-hidden="true"]'):
        tag.decompose()
    content = soup.select_one('main, [role="main"]') or soup.select_one('article') or soup.body or soup
    blocks = []
    remaining = 30000
    for tag in content.select('h1,h2,h3,h4,p,li,blockquote,pre,tr')[:150]:
        # Preserve the column boundaries needed to interpret factual tables.
        line = ' | '.join(' '.join(cell.get_text(' ', strip=True).split()) for cell in tag.find_all(['th', 'td'], recursive=False)) if tag.name == 'tr' else ' '.join(tag.get_text().split())
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
