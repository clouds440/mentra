"""Smoke-test rebuilt production images using disposable PostgreSQL resources.

No application database or application containers are used. A local deterministic
OpenAI-compatible stub verifies plumbing, not answer quality.
"""
import json
import threading
import time
from http.server import ThreadingHTTPServer
from uuid import uuid4
from pathlib import Path
import httpx
from testing.rag_runtime import docker, Provider, wait_ready, register


def main():
    suffix = uuid4().hex[:12]
    database = 'chat_runtime_test_' + suffix
    api = 'mentra-chat-verify-api-' + suffix
    frontend = 'mentra-chat-verify-web-' + suffix
    collection = 'mentra_chat_verify_' + suffix
    provider = ThreadingHTTPServer(('0.0.0.0', 18402), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    report = dict(checks=[])
    client = httpx.Client(base_url='http://127.0.0.1:18401', headers={'Origin':'http://localhost:5173'}, timeout=170)
    try:
        docker('exec', 'mentra-rag-test-postgres', 'psql', '-U', 'rag_test', '-d', 'rag_test', '-c', f'CREATE DATABASE {database}')
        env = dict(APP_ENV='test', DATABASE_URL=f'postgresql://rag_test:rag_test_only@host.docker.internal:15438/{database}',
            QDRANT_URL='http://host.docker.internal:16335', QDRANT_API_KEY='test-only', QDRANT_COLLECTION=collection,
            AI_MODEL='chat-test', AI_BASE_URL='http://host.docker.internal:18402/v1', AI_API_KEY='test-only')
        arguments = [arg for key, value in env.items() for arg in ['-e', f'{key}={value}']]
        docker('run', '-d', '--name', api, '-p', '127.0.0.1:18401:8000', *arguments, 'mentra-backend:latest')
        wait_ready(client); register(client)
        bootstrap = client.get('/api/v1/conversations/sync'); bootstrap.raise_for_status()
        assert bootstrap.json()['conversations'] == []
        report['checks'].append('startup applies chat migration and authenticated bootstrap is empty')
        cid, tid = str(uuid4()), str(uuid4())
        body = dict(conversation_id=cid, client_turn_id=tid, expected_revision=0, content='Remember this production-image question', retrieval=dict(mode='STANDARD'))
        sent = client.post('/api/v1/conversations/turns', json=body); sent.raise_for_status()
        page = sent.json(); assert page['turn']['state'] == 'SUCCEEDED', page
        assert len(page['items']) == 2 and page['incremental']
        repeated = client.post('/api/v1/conversations/turns', json=body); repeated.raise_for_status()
        assert repeated.json()['items'] == page['items']
        report['checks'].append('provider-backed turn is persisted and retry is idempotent')
        docker('restart', api); wait_ready(client)
        restored = client.get(f'/api/v1/conversations/{cid}/status'); restored.raise_for_status()
        assert restored.json()['items'] == page['items']
        report['checks'].append('backend restart preserves session, conversation and exact messages')
        delta = client.get('/api/v1/conversations/sync', params={'cursor': bootstrap.json()['cursor']}); delta.raise_for_status()
        assert delta.json()['conversations'][0]['id'] == cid
        report['checks'].append('committed changes replay from the original synchronization cursor')
        other = httpx.Client(base_url=client.base_url, headers=client.headers, timeout=30)
        try:
            register(other)
            assert other.get(f'/api/v1/conversations/{cid}/messages').status_code == 404
        finally:
            other.close()
        report['checks'].append('second account cannot access the conversation')
        revision = restored.json()['conversation']['revision']
        deleted = client.delete(f'/api/v1/conversations/{cid}', params={'expected_revision': revision}); deleted.raise_for_status()
        assert client.get(f'/api/v1/conversations/{cid}/messages').status_code == 404
        report['checks'].append('deletion excludes history and prevents reopening')
        docker('run', '-d', '--name', frontend, '-p', '127.0.0.1:15174:80', 'mentra-frontend:latest')
        with httpx.Client(base_url='http://127.0.0.1:15174', timeout=10) as web:
            for _ in range(40):
                try:
                    response = web.get('/chat/' + cid)
                    if response.status_code == 200: break
                except httpx.TransportError:
                    pass
                time.sleep(0.25)
            assert response.status_code == 200 and '<div id="root">' in response.text
            import re
            script = re.search(r'src="(/assets/[^"]+\.js)"', response.text).group(1)
            bundle = web.get(script); bundle.raise_for_status()
            assert '/api/v1/conversations' in bundle.text
        report['checks'].append('rebuilt Nginx image serves persistent chat routes and new API client bundle')
        Path('docs/chat-runtime-verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        client.close(); provider.shutdown(); provider.server_close()
        docker('rm', '-f', frontend, api, check=False)
        httpx.delete('http://127.0.0.1:16335/collections/'+collection, timeout=10)
        docker('exec', 'mentra-rag-test-postgres', 'psql', '-U', 'rag_test', '-d', 'rag_test', '-c', f'DROP DATABASE IF EXISTS {database} WITH (FORCE)', check=False)


if __name__ == '__main__': main()
