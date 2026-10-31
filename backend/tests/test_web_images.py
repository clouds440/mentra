"""Real assets, source provenance, deadlines and public-only destination safety."""
import asyncio
import io
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image
from app.web_search.images import ImageResolver, PublicNetworkBackend, image_candidates, valid_raster
from app.web_search.normalization import normalize_results
from app.web_search.schemas import SearchInput

NOW = datetime.now(timezone.utc)


def raster():
    stream = io.BytesIO()
    Image.new('RGB', (320,240), 'white').save(stream, format='PNG')
    return stream.getvalue()


def sources(url='https://tutorial.org/horse'):
    return normalize_results({'results':{'web':[{'url':url,'title':'Horse drawing','description':'Drawing tutorial'}]}},None,NOW)[0]


class CandidateTests(unittest.TestCase):
    def test_metadata_relative_lazy_and_original_links_without_icons(self):
        html = '<meta property="og:image" content="/preview.png"><article><img data-src="//cdn.tutorial.org/steps.png" alt="Construction steps"><img src="/logo.png" alt="logo"></article><div class="fullImageLink"><a href="/original.jpg">Original</a></div>'
        result = image_candidates(html,'https://tutorial.org/horse')
        self.assertEqual({item[0] for item in result},{'https://tutorial.org/preview.png','https://cdn.tutorial.org/steps.png','https://tutorial.org/original.jpg'})

    def test_raster_validation_rejects_html_and_tiny_tracking_assets(self):
        self.assertTrue(valid_raster(raster()))
        self.assertFalse(valid_raster(b'<html>not an image</html>'))
        stream=io.BytesIO()
        Image.new('RGB',(1,1)).save(stream,format='PNG')
        self.assertFalse(valid_raster(stream.getvalue()))
        stream=io.BytesIO()
        Image.new('RGB',(320,240)).save(stream,format='JPEG')
        self.assertFalse(valid_raster(stream.getvalue()[:-100]))

    def test_resized_variants_do_not_duplicate_the_same_image(self):
        result=image_candidates('<article><img src="/drawing.jpg"><img src="/drawing-475x237.jpg"></article>', 'https://tutorial.org/horse')
        self.assertEqual(result,[('https://tutorial.org/drawing.jpg','')])


class ResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_assets_are_verified_and_index_does_not_replace_useful_pages(self):
        requested=[]
        def remote(request):
            requested.append(str(request.url))
            if request.url.host=='api.openverse.org':
                return httpx.Response(200,json={'results':[]})
            if request.url.path=='/horse':
                return httpx.Response(200,text='<main><img src="/broken.png"><img src="/real.png" alt="Horse outline"></main>',headers={'content-type':'text/html'})
            if request.url.path=='/broken.png': return httpx.Response(403)
            return httpx.Response(200,content=raster(),headers={'content-type':'image/png'})
        result=await ImageResolver(httpx.MockTransport(remote)).enrich(sources(),SearchInput(query='horse drawing',include_images=True),NOW)
        self.assertEqual(result[0].images[0].url,'https://tutorial.org/real.png')
        self.assertEqual(result[0].images[0].caption,'Horse outline')
        self.assertIn('https://tutorial.org/broken.png',requested)

    async def test_blocked_page_can_use_verified_index_thumbnail_with_original_attribution(self):
        def remote(request):
            if request.url.host=='api.openverse.org':
                return httpx.Response(200,json={'results':[dict(foreign_landing_url='https://museum.org/horse',title='Mounted rider',url='https://cdn.museum.org/blocked.png',thumbnail='https://cdn.museum.org/preview.png')]})
            if request.url.path=='/preview.png':
                return httpx.Response(200,content=raster(),headers={'content-type':'image/png'})
            return httpx.Response(403)
        result=await ImageResolver(httpx.MockTransport(remote)).enrich(sources(),SearchInput(query='samurai horse',include_images=True),NOW)
        self.assertEqual(result[0].url,'https://museum.org/horse')
        self.assertEqual(result[0].images[0].url,'https://cdn.museum.org/preview.png')

    async def test_site_scope_and_no_results_are_honest(self):
        def remote(request):
            if request.url.host=='api.openverse.org':
                return httpx.Response(200,json={'results':[dict(foreign_landing_url='https://other.org/horse',url='https://other.org/horse.png')]})
            return httpx.Response(200,content=b'fake',headers={'content-type':'image/png'})
        result=await ImageResolver(httpx.MockTransport(remote)).enrich(sources(),SearchInput(query='horse',website='tutorial.org',include_images=True),NOW)
        self.assertEqual(len(result),1)
        self.assertFalse(result[0].images)

    async def test_deadline_retains_finished_assets_and_drains_siblings(self):
        cancelled=[]
        async def remote(request):
            if request.url.host=='api.openverse.org':
                try: await asyncio.Event().wait()
                finally: cancelled.append(True)
            if request.url.path=='/horse':
                return httpx.Response(200,text='<meta property="og:image" content="/real.png">',headers={'content-type':'text/html'})
            return httpx.Response(200,content=raster(),headers={'content-type':'image/png'})
        result=await ImageResolver(httpx.MockTransport(remote)).enrich(sources(),SearchInput(query='horse',include_images=True),NOW,timeout=.1)
        self.assertTrue(result[0].images)
        self.assertTrue(cancelled)

    async def test_private_redirect_is_rejected_before_fetch(self):
        visited=[]
        def remote(request):
            visited.append(str(request.url))
            return httpx.Response(302,headers={'location':'https://localhost/private'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(remote)) as client:
            with self.assertRaises(ValueError):
                await ImageResolver().read(client,'https://tutorial.org/start')
        self.assertEqual(visited,['https://tutorial.org/start'])

    async def test_page_cookies_are_not_sent_to_asset_requests(self):
        visited=[]
        def remote(request):
            visited.append(request)
            if request.url.host=='api.openverse.org': return httpx.Response(200,json={'results':[]})
            if request.url.path=='/horse':
                return httpx.Response(200,text='<img src="/real.png">',headers={'content-type':'text/html','set-cookie':'tracking=private; Path=/; Secure'})
            return httpx.Response(200,content=raster(),headers={'content-type':'image/png'})
        await ImageResolver(httpx.MockTransport(remote)).enrich(sources(),SearchInput(query='horse',include_images=True),NOW)
        self.assertTrue(any(request.url.path=='/real.png' for request in visited))
        self.assertTrue(all('cookie' not in request.headers for request in visited))

    async def test_large_asset_is_rejected_before_decoding(self):
        def remote(request): return httpx.Response(200,content=b'a'*(3*1024*1024+1),headers={'content-type':'image/png'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(remote)) as client:
            with self.assertRaises(ValueError):
                await ImageResolver().read(client,'https://tutorial.org/large.png',image=True)

    async def test_dns_pinning_rejects_private_and_mixed_answers(self):
        for addresses in (['127.0.0.1'],['93.184.216.34','169.254.169.254']):
            backend=PublicNetworkBackend()
            backend.inner=SimpleNamespace(connect_tcp=AsyncMock())
            resolver=AsyncMock(return_value=[(2,1,6,'',(address,443)) for address in addresses])
            with patch.object(asyncio.get_running_loop(),'getaddrinfo',resolver),self.assertRaises(ValueError):
                await backend.connect_tcp('tutorial.org',443)
            backend.inner.connect_tcp.assert_not_awaited()

    async def test_public_connection_is_pinned_to_verified_ip(self):
        backend=PublicNetworkBackend()
        backend.inner=SimpleNamespace(connect_tcp=AsyncMock(return_value='stream'))
        resolver=AsyncMock(return_value=[(2,1,6,'',('93.184.216.34',443))])
        with patch.object(asyncio.get_running_loop(),'getaddrinfo',resolver):
            self.assertEqual(await backend.connect_tcp('tutorial.org',443),'stream')
        self.assertEqual(backend.inner.connect_tcp.call_args.args[0],'93.184.216.34')
