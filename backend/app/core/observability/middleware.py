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
        from .payloads import capture, sensitive_values, redactions
        from urllib.parse import parse_qs
        headers = dict(scope.get('headers', []))
        protected = path.startswith('/api/v1/auth')
        request_is_json = b'application/json' in headers.get(b'content-type', b'')
        request_json = not protected and request_is_json
        response_json = False
        request_body, response_body = bytearray(), bytearray()
        request_size = response_size = 0
        query = parse_qs(scope.get('query_string', b'').decode('utf-8', errors='replace')) if not protected else {}
        secrets = sensitive_values(query)
        redaction_token = redactions.set((*redactions.get(), *secrets))
        def payload(buffer, size, allowed):
            if not allowed:
                return dict(capture='non-JSON or authentication body omitted', body_bytes=size)
            if size > 65536:
                return dict(capture='transport body exceeds capture cap', body_bytes=size)
            try:
                import json
                return json.loads(buffer) if buffer else None
            except (ValueError, UnicodeError):
                return dict(capture='invalid JSON', body_bytes=size)
        def route():
            return getattr(scope.get('route'), 'path', 'unmatched')
        def close(outcome, transport):
            collector.outcome = outcome
            incoming = payload(request_body,request_size,request_json)
            combined_secrets = [*secrets, *sensitive_values(incoming)]
            complete('request.completed', collector, level=logging.WARNING if outcome in ('failed', 'rejected', 'cancelled', 'timeout') else logging.INFO,
                     method=scope['method'], route=route(), status_code=status, transport_outcome=transport,
                     error_code=state['log_trace']['code'],
                     request=capture(dict(query=query,body=incoming), secrets=combined_secrets),
                     response=capture(payload(response_body,response_size,response_json), secrets=combined_secrets))
        async def traced_receive():
            nonlocal disconnected, request_size
            message = await receive()
            if message['type'] == 'http.disconnect':
                disconnected = True
            if message['type'] == 'http.request':
                chunk = message.get('body', b'')
                request_size += len(chunk)
                if request_is_json and len(request_body) < 65536:
                    request_body.extend(chunk[:65536-len(request_body)])
                if request_is_json and not message.get('more_body',False):
                    parsed = payload(request_body,request_size,True)
                    redactions.set((*redactions.get(), *sensitive_values(parsed)))
            return message
        async def traced_send(message):
            nonlocal status, sent, response_json, response_size
            if message['type'] == 'http.response.start':
                status = message['status']
                response_json = not protected and b'application/json' in dict(message.get('headers', [])).get(b'content-type', b'')
                message = dict(message, headers=[(k, v) for k, v in message.get('headers', []) if k.lower() != b'x-request-id'] + [(b'x-request-id', collector.request_id.encode())])
                emit('request.response_started', status_code=status, route=route())
            await send(message)
            if message['type'] == 'http.response.body':
                chunk = message.get('body', b'')
                response_size += len(chunk)
                if response_json and len(response_body) < 65536:
                    response_body.extend(chunk[:65536-len(response_body)])
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
            redactions.reset(redaction_token)


class ObservedFastAPI(FastAPI):
    def build_middleware_stack(self):
        return RequestTracing(super().build_middleware_stack())
