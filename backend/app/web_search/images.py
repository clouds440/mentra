"""Resolve real image assets from public evidence, with bounded, DNS-pinned reads."""
import asyncio
import io
import ipaddress
import json
import re
import socket
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpcore
import httpx
from PIL import Image
from app.core.logging import workflow_logger
from .normalization import clean_text, normalize_results
from .schemas import WebImage
from .urls import public_url, in_scope

MAX_IMAGE_BYTES = 3 * 1024 * 1024


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Validate every DNS answer and connect to that exact public IP, retaining TLS SNI."""
    def __init__(self):
        self.inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if port != 443:
            raise ValueError('Only public HTTPS assets are supported.')
        async with asyncio.timeout(timeout):
            answers = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
            addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
            if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise ValueError('Nonpublic image destination.')
            addresses.sort(key=lambda address: ipaddress.ip_address(address).version)
            for index, address in enumerate(addresses[:3]):
                try:
                    return await self.inner.connect_tcp(address, port, timeout, local_address, socket_options)
                except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError):
                    if index == min(2, len(addresses) - 1):
                        raise

    async def connect_unix_socket(self, *args, **kwargs):
        raise ValueError('Local sockets are unavailable.')

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


class PublicTransport(httpx.AsyncHTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False, retries=0)
        # httpx 0.28/httpcore 1.x expose the backend on the transport pool.
        # TLS hostname verification still uses the original request hostname.
        self._pool = httpcore.AsyncConnectionPool(network_backend=PublicNetworkBackend(),
            max_connections=6, max_keepalive_connections=0)


def image_candidates(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for tag in soup.select('meta[property="og:image"], meta[name="twitter:image"], link[rel="image_src"]'):
        rows.append((tag.get('content') or tag.get('href'), ''))
    # Wikimedia and other galleries expose original file links in the content.
    for tag in soup.select('.fullImageLink a[href], a[download][href]'):
        rows.append((tag.get('href'), tag.get_text(' ', strip=True)))
    content = soup.select_one('article, main, #content') or soup
    for tag in content.select('img')[:60]:
        label = clean_text(tag.get('alt'), 200)
        if any(word in (label + ' ' + ' '.join(tag.get('class', []))).lower() for word in ('logo', 'avatar', 'favicon', 'tracking', 'emoji', 'icon')):
            continue
        if any(str(tag.get(axis, '')).isdigit() and int(tag[axis]) < 160 for axis in ('width', 'height')):
            continue
        rows.append((tag.get('data-src') or tag.get('data-lazy-src') or tag.get('src'), label))
    seen, candidates = set(), []
    for raw, label in rows:
        if not isinstance(raw, str):
            continue
        try:
            url, _ = public_url(urljoin(base, raw))
            identity = re.sub(r'-\d+x\d+(?=\.[a-zA-Z0-9]+(?:\?|$))', '', url)
            identity = re.sub(r'/\d+px-', '/', identity)
            if not url.startswith('https://') or identity in seen or url.lower().split('?')[0].endswith('.svg'):
                continue
            seen.add(identity)
            candidates.append((url, label))
        except ValueError:
            continue
    return candidates[:5]


def valid_raster(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('JPEG', 'PNG', 'WEBP', 'GIF', 'AVIF') or min(image.size) < 160 or image.width * image.height > 8_000_000:
                return False
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()  # JPEG.verify alone does not detect truncated pixel data.
        return True
    except (ValueError, OSError, Image.DecompressionBombError):
        return False


class ImageResolver:
    def __init__(self, transport=None):
        self.transport = transport

    async def read(self, client, url, *, image=False, json_data=False):
        limit = MAX_IMAGE_BYTES if image else 768 * 1024
        for _ in range(4):
            url, _ = public_url(url)
            if not url.startswith('https://'):
                raise ValueError('HTTPS required.')
            async with client.stream('GET', url, headers={'Accept-Encoding':'identity'}) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location', ''))
                    continue
                response.raise_for_status()
                length = response.headers.get('content-length', '')
                if length.isdigit() and int(length) > limit:
                    raise ValueError('Asset exceeds the bounded read size.')
                mime = response.headers.get('content-type', '').split(';')[0].lower()
                if image and mime not in ('image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif'):
                    raise ValueError('Not an embeddable raster image.')
                if not image and mime not in (('application/json',) if json_data else ('text/html', 'application/xhtml+xml')):
                    raise ValueError('Unexpected page response.')
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError('Asset exceeds the bounded read size.')
                if image and not await asyncio.to_thread(valid_raster, data):
                    raise ValueError('Invalid or unsuitable image data.')
                return url, bytes(data)
        raise ValueError('Too many redirects.')

    async def enrich(self, sources, request, now, *, timeout=8):
        # Normal searches never pay for these requests. On expiry, already
        # verified images survive; broken/blocked pages do not erase web results.
        results = [source.model_copy(deep=True) for source in sources]
        semaphore = asyncio.Semaphore(3)
        transport = self.transport or PublicTransport()
        remaining_requests, failures = 24, {}
        def failed(error, kind):
            reason = str(error.response.status_code) if isinstance(error, httpx.HTTPStatusError) else type(error).__name__
            key = f'{kind}:{reason}'
            failures[key] = failures.get(key, 0) + 1
        async def strip_credentials(outgoing):
            nonlocal remaining_requests
            if remaining_requests <= 0:
                raise ValueError('Image retrieval request allowance exhausted.')
            remaining_requests -= 1
            for header in ('cookie', 'authorization', 'proxy-authorization'):
                outgoing.headers.pop(header, None)
        async with httpx.AsyncClient(transport=transport, timeout=3, follow_redirects=False,
                trust_env=False, event_hooks={'request':[strip_credentials]},
                headers={'User-Agent':'Mentra/1.0 (educational image references)'}) as client:
            async def resolve(source, candidates=None):
                try:
                    async with semaphore:
                        target = 2 if candidates is None else 1
                        if candidates is None:
                            page, data = await self.read(client, source.url)
                            candidates = image_candidates(data.decode('utf-8', errors='replace'), page)
                        for url, caption in candidates[:3]:
                            try:
                                asset, _ = await self.read(client, url, image=True)
                                if asset not in {item.url for item in source.images}:
                                    source.images.append(WebImage(url=asset, caption=clean_text(caption,200) or source.title))
                                if len(source.images) >= target:
                                    break
                            except (httpx.HTTPError, ValueError, OSError) as error:
                                failed(error, 'asset')
                                continue
                except (httpx.HTTPError, ValueError, OSError) as error:
                    failed(error, 'page')

            async def index():
                # A real public image index supplements ordinary web pages.
                # Never force one host, and preserve a user-specified site scope.
                try:
                    query = str(httpx.URL('https://api.openverse.org/v1/images/', params={'q':request.query,'page_size':8,'mature':'false'}))
                    _, data = await self.read(client, query, json_data=True)
                    payload = json.loads(data)
                    if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
                        raise ValueError('Invalid image-index response.')
                    candidates = []
                    for item in payload['results'][:8]:
                        if not isinstance(item, dict):
                            continue
                        try:
                            page, host = public_url(item.get('foreign_landing_url', ''))
                        except (ValueError, TypeError):
                            continue
                        if not in_scope(host, request.website):
                            continue
                        normalized, _ = normalize_results({'results':{'web':[dict(url=page,title=item.get('title'),description='Image-index result; check the source page for attribution and reuse terms.')]}}, request.website, now)
                        if not normalized:
                            continue
                        source = normalized[0]
                        links = [(item.get(key), source.title) for key in ('url','thumbnail') if isinstance(item.get(key), str)]
                        candidates.append((source, links))
                    try:
                        await asyncio.gather(*(resolve(source, links) for source, links in candidates))
                    finally:
                        for source, _ in candidates:
                            if source.images:
                                existing = next((item for item in results if item.url == source.url), None)
                                if existing:
                                    existing.images = source.images
                                else:
                                    results.append(source)
                except (httpx.HTTPError, ValueError, OSError, TypeError) as error:
                    failed(error, 'index')

            tasks = [asyncio.create_task(resolve(source)) for source in results]
            tasks.append(asyncio.create_task(index()))
            try:
                deadline = asyncio.get_running_loop().time() + timeout
                pending = set(tasks)
                while pending and asyncio.get_running_loop().time() < deadline:
                    _, pending = await asyncio.wait(pending,
                        timeout=max(0, deadline - asyncio.get_running_loop().time()),
                        return_when=asyncio.FIRST_COMPLETED)
                    ready = [source for source in results if source.images]
                    if sum(len(source.images) for source in ready) >= 4 and len({source.domain for source in ready}) >= 2:
                        break
            finally:
                for task in tasks:
                    if not task.done(): task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        workflow_logger.event('web_search.image_resolution', request_count=24-remaining_requests,
            failures=failures, verified_images=sum(len(source.images) for source in results))
        # Prefer successfully verified assets, with different source sites first.
        ordered = []
        for with_images in (True, False):
            diverse, rest, hosts = [], [], set()
            for source in results:
                if bool(source.images) != with_images:
                    continue
                if source.domain in hosts:
                    rest.append(source)
                else:
                    diverse.append(source)
                    hosts.add(source.domain)
            ordered.extend(diverse + rest)
        return ordered[:5]
