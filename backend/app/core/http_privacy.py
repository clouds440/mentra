"""Private API responses, including streamed and framework error responses."""
from starlette.datastructures import MutableHeaders


class PrivateApiResponses:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        private = scope['type'] == 'http' and scope.get('path', '').startswith('/api/v1/') and not scope['path'].startswith('/api/v1/health')
        async def private_send(message):
            if private and message['type'] == 'http.response.start':
                MutableHeaders(scope=message)['Cache-Control'] = 'no-store'
            await send(message)
        await self.app(scope, receive, private_send)
