import asyncio
import logging
from fastapi import FastAPI
from .context import Collector, current, span, identifier
from .events import emit
from .sanitization import error_metadata
from .steps import complete, setting


class RequestTracing:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope.get('path', '')
        quiet = (path in ('/api/v1/health', '/api/v1/health/ready') and not setting('log_health_requests', False)) or (
            scope['method'] == 'GET' and ('/sync' in path or '/turns/' in path or '/rag/jobs/' in path) and not setting('log_poll_requests', False))
        collector = Collector('http.request', request_id=identifier(), quiet=quiet, maximum=setting('log_summary_max_steps', 500))
        token, span_token = current.set(collector), span.set(None)
        state = scope.setdefault('state', {})
        state['log_trace'] = dict(reported=False, code=None)
        status, sent, disconnected = None, False, False
        def route():
            return getattr(scope.get('route'), 'path', 'unmatched')
        def close(outcome, transport):
            collector.outcome = outcome
            complete('request.completed', collector, level=logging.WARNING if outcome in ('failed', 'rejected', 'cancelled', 'timeout') else logging.INFO,
                     method=scope['method'], route=route(), status_code=status, transport_outcome=transport,
                     error_code=state['log_trace']['code'])
        async def traced_receive():
            nonlocal disconnected
            message = await receive()
            if message['type'] == 'http.disconnect':
                disconnected = True
            return message
        async def traced_send(message):
            nonlocal status, sent
            if message['type'] == 'http.response.start':
                status = message['status']
                message = dict(message, headers=[(k, v) for k, v in message.get('headers', []) if k.lower() != b'x-request-id'] + [(b'x-request-id', collector.request_id.encode())])
                emit('request.response_started', status_code=status, route=route())
            await send(message)
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                sent = True
                semantic = state['log_trace'].get('outcome')
                close(semantic or ('failed' if status >= 500 else 'rejected' if status >= 400 else 'deferred' if status == 202 else collector.outcome if collector.outcome != 'unknown' else 'success'), 'complete')
        emit('request.started', method=scope['method'], route='unresolved')
        try:
            await self.app(scope, traced_receive, traced_send)
        except BaseException as error:
            if not state['log_trace']['reported']:
                from .errors import mark_reported
                mark_reported(error)
                emit('request.post_response_error' if sent else 'request.error', level=logging.ERROR, error=error_metadata(error))
                state['log_trace']['reported'] = True
            if not sent:
                close('cancelled' if isinstance(error, asyncio.CancelledError) else 'failed', 'disconnected' if disconnected else 'incomplete')
            raise
        finally:
            if not collector.closed:
                close('cancelled' if disconnected else 'failed', 'disconnected' if disconnected else 'incomplete')
            span.reset(span_token)
            current.reset(token)


class ObservedFastAPI(FastAPI):
    def build_middleware_stack(self):
        return RequestTracing(super().build_middleware_stack())
