"""Bound multipart transport before Starlette spools an unbounded upload."""
from starlette.responses import JSONResponse


class UploadTooLarge(Exception):
    pass


class MaterialUploadLimit:
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum + 64 * 1024

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        guarded = scope['type'] == 'http' and scope.get('method') == 'POST' and (
            path == '/api/v1/documents' or path.startswith('/api/v1/documents/') and path.endswith('/versions'))
        if not guarded:
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            length = self.maximum + 1
        response = JSONResponse({'error': {'code': 'RAG_FILE_TOO_LARGE', 'message': 'Material exceeds the upload size limit.'}}, status_code=413)
        if length > self.maximum:
            return await response(scope, receive, send)
        size = 0
        too_large = False

        async def bounded_receive():
            nonlocal size, too_large
            message = await receive()
            if message['type'] == 'http.request':
                size += len(message.get('body', b''))
                if size > self.maximum:
                    too_large = True
                    raise UploadTooLarge()
            return message

        async def guarded_send(message):
            # FastAPI may normalize form-parser exceptions into HTTP errors. Do
            # not let that hide the actual transport-size failure.
            if not too_large:
                await send(message)

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except UploadTooLarge:
            too_large = True
        if too_large:
            await response(scope, receive, send)
