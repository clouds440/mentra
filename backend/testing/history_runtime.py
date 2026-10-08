"""Actual rebuilt image, OpenAI tool protocol, PostgreSQL and restart verification.

Uses only uniquely named disposable resources and dedicated test services.
"""
import json
import threading
import time
import os
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
import httpx
from testing.rag_runtime import docker, wait_ready, register


class ToolProvider(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        tools = body.get('tools', [])
        names = [x['function']['name'] for x in tools]
        self.calls.append(names)
        message = dict(role='assistant', content='A general grounded answer.')
        finish = 'stop'
        if 'Admission' in names:
            data = json.loads(body['messages'][-1]['content'])
            message = dict(role='assistant', content=None, tool_calls=[dict(id='verify_call', type='function', function=dict(name='Admission', arguments=json.dumps(dict(
                supported=True, explicit_user_statement=not data['user_message'].lower().startswith('maybe'),
                sensitive='diagnosis' in data['user_message'].lower(), explicit_remember_request=data['user_message'].lower().startswith('remember'),
                durable=True, contradicts_existing=False, profile_field=False, valid_until=None))))])
            finish = 'tool_calls'
        elif any(x['role'] == 'tool' for x in body['messages']):
            result = json.loads(next(x['content'] for x in reversed(body['messages']) if x['role'] == 'tool'))
            if 'memories' in result:
                text = result['memories'][0]['content']+' [['+result['memories'][0]['token']+']]' if result['memories'] else 'No saved memories matched.'
            elif 'windows' in result:
                text = 'Found earlier chat [['+result['windows'][0]['token']+']]' if result['windows'] else 'No previous conversations matched.'
            else:
                text = 'Memory '+result.get('outcome', 'unavailable')+'.'
            message['content'] = text
        elif 'user_memory' in names:
            system = body['messages'][0]['content']
            context = json.loads(system[system.rfind('\n\n{')+2:])
            question = next(x['content'] for x in reversed(body['messages']) if x['role'] == 'user')
            lower = question.lower()
            if lower.startswith('remember'):
                name, args = 'user_memory', dict(action='remember', content=question, category='preference', evidence_quote=question,
                    evidence_message_id=context['history_scope']['current_user_message_id'])
            elif lower.startswith('recall memories about '):
                name, args = 'user_memory', dict(action='recall', query=question[22:])
            else:
                name, args = 'history_lookup', dict(scope='all_chats', query='diagrams')
            message = dict(role='assistant', content=None, tool_calls=[dict(id='runtime_tool_call', type='function', function=dict(name=name, arguments=json.dumps(args)))])
            finish = 'tool_calls'
        response = json.dumps(dict(id='chatcmpl-history-test', object='chat.completion', created=int(time.time()), model='history-test',
            choices=[dict(index=0, message=message, finish_reason=finish)], usage=dict(prompt_tokens=100, completion_tokens=50, total_tokens=150))).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers(); self.wfile.write(response)

    def log_message(self, *_args):
        pass


def main():
    suffix = uuid4().hex[:12]
    database = 'history_runtime_test_'+suffix
    api = 'mentra-history-verify-api-'+suffix
    web = 'mentra-history-verify-web-'+suffix
    collection = 'mentra_history_verify_'+suffix
    provider = ThreadingHTTPServer(('0.0.0.0', 18402), ToolProvider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    report = dict(provider='Deterministic local HTTP provider; verifies tool protocol, not model quality', checks=[])
    client = httpx.Client(base_url='http://127.0.0.1:18401', headers={'Origin':'http://localhost:5173'}, timeout=170)
    def turn(text):
        cid = str(uuid4())
        result = client.post('/api/v1/conversations/turns', json=dict(conversation_id=cid, client_turn_id=str(uuid4()), expected_revision=0, content=text, retrieval=dict(mode='STANDARD')))
        result.raise_for_status()
        page = result.json()
        assert page['turn']['state'] == 'SUCCEEDED', page['turn'].get('error')
        return cid, page
    try:
        docker('exec','mentra-rag-test-postgres','psql','-U','rag_test','-d','rag_test','-c',f'CREATE DATABASE {database}')
        env = dict(APP_ENV='test', DATABASE_URL=f'postgresql://rag_test:rag_test_only@host.docker.internal:15438/{database}',
            QDRANT_URL='http://host.docker.internal:16335', QDRANT_API_KEY='test-only', QDRANT_COLLECTION=collection,
            AI_MODEL='history-test', AI_BASE_URL='http://host.docker.internal:18402/v1', AI_API_KEY='test-only', AI_MAX_RETRIES='0')
        env.update(FRONTEND_ORIGIN='http://127.0.0.1:15174', CORS_ORIGINS='http://localhost:5173,http://127.0.0.1:15174')
        arguments = [item for key, value in env.items() for item in ['-e',f'{key}={value}']]
        docker('run','-d','--name',api,'-p','127.0.0.1:18401:8000',*arguments,'mentra-backend:latest')
        wait_ready(client); register(client)
        report['checks'].append('Rebuilt image starts with automatic migration 0006, auth and onboarding')
        cid, page = turn('Remember that I prefer diagrams for complex systems.')
        assert 'saved' in page['items'][-1]['content'], page['items'][-1]['content']
        response = client.get('/api/v1/memories'); response.raise_for_status()
        memory = response.json()['items'][0]
        assert memory['status'] == 'active'
        report['checks'].append('Actual ChatOpenAI tool binding, semantic structured validation and evidence-backed persistence')
        recall_chat, recalled = turn('Recall memories about diagrams')
        assert recalled['items'][-1]['memory_references'][0]['memory_id'] == memory['id']
        history_chat, history = turn('Find past chats about diagrams')
        assert history['items'][-1]['history_references']
        report['checks'].append('Actual tool-result pairing, memory recall and cross-chat history with distinct M/H references')
        docker('restart', api); wait_ready(client)
        response = client.get('/api/v1/memories/'+memory['id']); response.raise_for_status()
        assert response.json()['content'] == memory['content']
        assert client.get(f'/api/v1/conversations/{recall_chat}/status').json()['items'][-1]['memory_references']
        report['checks'].append('Restart preserves memories, saved evidence, chat references and session')
        other = httpx.Client(base_url=client.base_url, headers=client.headers, timeout=30)
        try:
            register(other)
            assert other.get('/api/v1/memories/'+memory['id']).status_code == 404
            assert other.get(f'/api/v1/memories/history/{cid}', params={'sequence':1}).status_code == 404
        finally:
            other.close()
        report['checks'].append('Second account cannot retrieve memory detail or history references')
        deleted = client.delete(f'/api/v1/conversations/{cid}', params={'expected_revision':page['conversation']['revision']}); deleted.raise_for_status()
        response = client.get('/api/v1/memories/'+memory['id']); response.raise_for_status()
        assert response.json()['evidence'][0]['source_deleted']
        report['checks'].append('Chat deletion preserves active memory and detached minimum evidence')
        edited = client.patch('/api/v1/memories/'+memory['id'], json=dict(expected_revision=1, content='I prefer annotated diagrams.')); edited.raise_for_status()
        assert edited.json()['revision'] == 2
        assert client.patch('/api/v1/memories/'+memory['id'], json=dict(expected_revision=1, content='Stale update')).status_code == 409
        client.delete('/api/v1/memories/'+memory['id'], params={'expected_revision':2}).raise_for_status()
        assert client.get('/api/v1/memories/'+memory['id']).status_code == 404
        report['checks'].append('Manual edit, optimistic revision conflict and permanent memory/evidence purge')
        docker('run','-d','--name',web,'-p','127.0.0.1:15174:80','mentra-frontend:latest')
        with httpx.Client(base_url='http://127.0.0.1:15174', timeout=10) as frontend:
            for _ in range(40):
                try:
                    response = frontend.get('/settings?tab=memories')
                    if response.status_code == 200: break
                except httpx.TransportError: pass
                time.sleep(.25)
            assert response.status_code == 200
            import re
            script = re.search(r'src="(/assets/[^\"]+\.js)"', response.text).group(1)
            bundle = frontend.get(script); bundle.raise_for_status()
            settings_chunk = re.search(r'(MemoriesSettings-[A-Za-z0-9_-]+\.js)', bundle.text).group(1)
            settings_script = frontend.get('/assets/'+settings_chunk).text
            assert 'Your memories' in settings_script
            modules = [bundle.text, settings_script]
            for match in set(re.findall(r'((?:memories|MemoryDetails)-[A-Za-z0-9_-]+\.js)', bundle.text+settings_script)):
                modules.append(frontend.get('/assets/'+match).text)
            assert any('/api/v1/memories' in module for module in modules)
        report['checks'].append('Rebuilt Nginx frontend serves Settings deep link and memory API/UI bundle')
        browser_env = dict(os.environ, HISTORY_RUNTIME_COOKIE='; '.join(f'{key}={value}' for key,value in client.cookies.items()))
        result = subprocess.run(['node','frontend/tests/history-runtime-browser.mjs'],env=browser_env,text=True,capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        report['checks'].append('Browser on rebuilt Nginx image verifies manual CRUD, reload, confirmation and tool-written memory against rebuilt API via test-only URL proxy')
        report['images'] = {name:docker('inspect','--format','{{.Image}}',container) for name,container in [('mentra-backend:latest',api),('mentra-frontend:latest',web)]}
        assert any('Admission' in x for x in ToolProvider.calls)
        Path('docs/history-runtime-verification.json').write_text(json.dumps(report,indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally:
        client.close(); provider.shutdown(); provider.server_close()
        docker('rm','-f',web,api,check=False)
        httpx.delete('http://127.0.0.1:16335/collections/'+collection,timeout=10)
        docker('exec','mentra-rag-test-postgres','psql','-U','rag_test','-d','rag_test','-c',f'DROP DATABASE IF EXISTS {database} WITH (FORCE)',check=False)


if __name__ == '__main__': main()
