"""Bound the single multipart endpoint before form parser spooling."""

from starlette.responses import JSONResponse


class UploadTooLarge(Exception):
    pass


class FileUploadLimit:
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum + 64 * 1024

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("path") != "/api/v1/files/uploads"
            or scope.get("method") != "POST"
        ):
            return await self.app(scope, receive, send)
        response = JSONResponse(
            {
                "error": {
                    "code": "FILES_SIZE",
                    "message": "This file exceeds the upload size limit.",
                }
            },
            status_code=413,
        )
        try:
            length = int(dict(scope["headers"]).get(b"content-length", b"0"))
        except ValueError:
            length = -1
        if length < 0 or length > self.maximum:
            return await response(scope, receive, send)
        size, exceeded = 0, False

        async def bounded_receive():
            nonlocal size, exceeded
            message = await receive()
            size += len(message.get("body", b""))
            if size > self.maximum:
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
