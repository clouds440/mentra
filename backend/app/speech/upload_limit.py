"""Bound speech multipart uploads, including chunked bodies, before parsing/spooling."""
from starlette.responses import JSONResponse
from app.rag.upload_limit import UploadTooLarge


class SpeechUploadLimit:
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum + 64 * 1024

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') != '/api/v1/speech/transcriptions':
            return await self.app(scope, receive, send)
        response = JSONResponse({'error': {'code': 'SPEECH_SIZE', 'message': 'Recording exceeds the upload limit.'}},
                                status_code=413, headers={'Cache-Control': 'no-store'})
        try:
            size = int(dict(scope['headers']).get(b'content-length', b'0'))
        except ValueError:
            size = self.maximum + 1
        if size > self.maximum:
            return await response(scope, receive, send)
        size, exceeded = 0, False

        async def bounded_receive():
            nonlocal size, exceeded
            message = await receive()
            size += len(message.get('body', b''))
            if size > self.maximum:
                exceeded = True
                raise UploadTooLarge()
            return message

        async def guarded_send(message):
            if not exceeded:
                if message['type'] == 'http.response.start':
                    message = dict(message, headers=[(key, value) for key, value in message.get('headers', [])
                                                      if key.lower() != b'cache-control'] + [(b'cache-control', b'no-store')])
                await send(message)

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except UploadTooLarge:
            exceeded = True
        if exceeded:
            await response(scope, receive, send)
