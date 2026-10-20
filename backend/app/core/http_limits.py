"""Bound JSON bytes before framework parsing, including chunked requests."""
from starlette.responses import JSONResponse
from app.files.upload_limit import UploadTooLarge


class JsonBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        media = headers.get(b'content-type', b'').split(b';')[0].lower()
        if media != b'application/json' and not media.endswith(b'+json'):
            return await self.app(scope, receive, send)
        path = scope.get('path', '')
        maximum = 20 * 1024 * 1024 if path == '/api/v1/chat' else 2 * 1024 * 1024
        if path.startswith('/api/v1/assessments/'):
            maximum = 1024 * 1024
        response = JSONResponse({'error': {'code': 'REQUEST_TOO_LARGE', 'message': 'The request exceeds its size limit.'}}, status_code=413)
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            length = maximum + 1
        if length < 0 or length > maximum:
            return await response(scope, receive, send)
        size, exceeded = 0, False

        async def bounded_receive():
            nonlocal size, exceeded
            message = await receive()
            if message['type'] == 'http.request':
                size += len(message.get('body', b''))
                if size > maximum:
                    exceeded = True
                    raise UploadTooLarge()
            return message

        async def guarded_send(message):
            if not exceeded:
                await send(message)

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except UploadTooLarge:
            exceeded = True
        if exceeded:
            await response(scope, receive, send)
