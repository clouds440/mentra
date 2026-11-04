import unittest

import httpx

from app.web_search.preview import check_preview


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
