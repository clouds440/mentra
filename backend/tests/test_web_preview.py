import unittest

import httpx

from app.web_search.preview import check_preview, read_publisher, read_publisher_result


class WebPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_checks_final_headers_without_loading_publisher_body(self):
        class UnreadableBody(httpx.AsyncByteStream):
            async def __aiter__(self):
                raise AssertionError('Publisher body should never be read')
                yield b''

        def remote(request):
            self.assertNotIn('cookie', request.headers)
            self.assertNotIn('authorization', request.headers)
            if request.url.path == '/old':
                return httpx.Response(302, headers={'location': 'https://articles.example.org/latest', 'set-cookie': 'token=private; Domain=example.org; Secure'})
            return httpx.Response(200, headers={'content-type': 'text/html; charset=utf-8'}, stream=UnreadableBody())

        result = await check_preview('https://example.org/old', transport=httpx.MockTransport(remote))
        self.assertEqual((result.status, result.url), ('available', 'https://articles.example.org/latest'))

    async def test_reports_frame_restrictions_and_unavailable_responses(self):
        for status, headers, expected in (
            (200, {'x-frame-options': 'SAMEORIGIN'}, 'blocked'),
            (200, {'content-security-policy': "default-src 'self'; frame-ancestors 'none'"}, 'blocked'),
            (200, {'content-security-policy': "frame-ancestors *, frame-ancestors 'self'"}, 'blocked'),
            (200, {'content-security-policy': 'frame-ancestors *'}, 'available'),
            (200, {'content-security-policy-report-only': "frame-ancestors 'none'"}, 'available'),
            (200, {'content-disposition': 'attachment'}, 'unavailable'),
            (200, {'content-type': 'application/octet-stream'}, 'unavailable'),
            (403, {}, 'unavailable'),
        ):
            with self.subTest(status=status, headers=headers):
                transport = httpx.MockTransport(lambda _: httpx.Response(status, headers={'content-type': 'text/html', **headers}))
                result = await check_preview('https://example.org/article', transport=transport)
                self.assertEqual(result.status, expected)

    async def test_rejects_insecure_and_private_redirects(self):
        for location in ('http://example.org/article', 'https://127.0.0.1/', 'https://example.org:8080/article'):
            with self.subTest(location=location):
                def remote(request):
                    self.assertEqual(str(request.url), 'https://example.org/start')
                    return httpx.Response(302, headers={'location': location})

                result = await check_preview('https://example.org/start', transport=httpx.MockTransport(remote))
                self.assertEqual(result.status, 'unavailable')

    async def test_reader_returns_only_plain_text_and_public_links_from_blocked_page(self):
        def remote(request):
            if request.url.path == '/start':
                return httpx.Response(302, headers={'location': '/article'})
            return httpx.Response(200, headers={'content-type': 'text/html', 'x-frame-options': 'DENY'}, text="""
                <nav>Publisher navigation</nav>
                <article><h1>Selected heading</h1><p>A useful <strong>excerpt</strong>.</p>
                <script>window.run()</script><p hidden>Invisible text</p>
                <a href="/next">Related page</a><a href="https://127.0.0.1/">Private</a></article>""")

        result = await read_publisher('https://example.org/start', transport=httpx.MockTransport(remote))
        self.assertEqual(result, dict(url='https://example.org/article', blocks=['Selected heading', 'A useful excerpt.'],
            links=[dict(url='https://example.org/next', title='Related page')]))

    async def test_reader_rejects_invalid_compression_and_nontext_documents(self):
        for headers in ({'content-type': 'text/html', 'content-encoding': 'gzip'}, {'content-type': 'application/pdf'}):
            transport = httpx.MockTransport(lambda _: httpx.Response(200, headers=headers))
            self.assertIsNone(await read_publisher('https://example.org/file', transport=transport))

    async def test_valid_compression_and_main_content_work_across_unrelated_publishers(self):
        import gzip, zlib
        html = b'<body><article>Unrelated sidebar</article><main><h1>Release notes</h1><p>Version 12.3 is available.</p></main></body>'
        for host, coding, encode in (('docs.python.org','gzip',gzip.compress),('www.metoffice.gov.uk','deflate',zlib.compress),('en.wikipedia.org','identity',lambda value:value)):
            with self.subTest(host=host,coding=coding):
                def remote(request):
                    self.assertNotIn('cookie',request.headers)
                    self.assertNotIn('authorization',request.headers)
                    return httpx.Response(200,headers={'content-type':'text/html','content-encoding':coding},stream=httpx.ByteStream(encode(html)))
                result = await read_publisher_result('https://'+host+'/public-page',transport=httpx.MockTransport(remote))
                self.assertEqual(result.status,'ok')
                self.assertEqual(result.page['blocks'],['Release notes','Version 12.3 is available.'])

    async def test_compression_bomb_is_bounded_and_reported_truncated(self):
        import gzip
        data = gzip.compress(b'<main><p>'+b'x'*(2*1024*1024)+b'</p></main>')
        transport = httpx.MockTransport(lambda _:httpx.Response(200,headers={'content-type':'text/html','content-encoding':'gzip'},stream=httpx.ByteStream(data)))
        result = await read_publisher_result('https://example.org/page',transport=transport)
        self.assertEqual(result.status,'ok')
        self.assertTrue(result.truncated)
        self.assertLessEqual(sum(map(len,result.page['blocks'])),30000)

    async def test_access_denied_timeout_and_unsupported_are_distinct(self):
        for code, expected in ((403,'blocked'),(429,'rate_limited'),(404,'not_found'),(503,'unavailable')):
            with self.subTest(code=code):
                result=await read_publisher_result('https://example.org/page',transport=httpx.MockTransport(lambda _:httpx.Response(code)))
                self.assertEqual(result.status,expected)
                self.assertEqual(result.http_status,code)
                self.assertIsNone(result.page)
        def timeout(request): raise httpx.ReadTimeout('test')
        result=await read_publisher_result('https://example.org/page',transport=httpx.MockTransport(timeout))
        self.assertEqual(result.status,'timeout')
        result=await read_publisher_result('https://example.org/page',transport=httpx.MockTransport(lambda _:httpx.Response(200,headers={'content-type':'application/pdf'})))
        self.assertEqual(result.status,'unsupported')
