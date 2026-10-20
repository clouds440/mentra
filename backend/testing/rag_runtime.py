"""Verify production API/worker processes and private Cloudinary originals.

Requires the mentra-rag-verify image and dedicated mentra-rag-test-postgres /
mentra-rag-test-qdrant containers. Creates and removes only uniquely named test
database, collection and API/worker containers. Uses server-side CLOUDINARY_URL.
The chat provider is a deterministic local HTTP stub, not a quality judge.
"""
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import httpx


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


class Provider(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        system = body['messages'][0]['content']
        marker = system.rfind('\n\n{')
        sources = json.loads(system[marker + 2:])['study_sources']['sources'] if marker >= 0 else []
        content = f"The notes say: {sources[0]['excerpt']} [[{sources[0]['token']}]]" if sources else 'No supporting Library material was found.'
        response = json.dumps(dict(id='chatcmpl-rag-test', object='chat.completion', created=int(time.time()), model='rag-test',
            choices=[dict(index=0, message=dict(role='assistant', content=content), finish_reason='stop')],
            usage=dict(prompt_tokens=10, completion_tokens=10, total_tokens=20))).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(response))); self.end_headers(); self.wfile.write(response)

    def log_message(self, *_args):
        pass


def wait_ready(client):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            response = client.get('/api/v1/health/ready')
            if response.status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    raise RuntimeError('Isolated production API did not become ready.')


def register(client):
    response = client.post('/api/v1/auth/register', headers={'X-Mentra-Session':'cookie'},
        json=dict(username='runtime_' + uuid4().hex[:10], password='runtime test unique passphrase'))
    response.raise_for_status()
    profile = client.get('/api/v1/student-profile').json()
    response = client.put('/api/v1/student-profile/details', json=dict(expected_version=profile['version'], details=dict(
        education_level='undergraduate', field_of_study='Computer science', learning_goal='Understand Python programming',
        learning_preference='examples_first', explanation_depth='standard')))
    response.raise_for_status()
    client.post('/api/v1/student-profile/calibration/skip', json=dict(expected_version=response.json()['version'])).raise_for_status()


def main():
    suffix = uuid4().hex[:12]
    image = os.environ.get('RAG_RUNTIME_IMAGE', 'mentra-rag-verify:latest')
    database = 'rag_runtime_test_' + suffix
    collection = 'mentra_runtime_test_' + suffix
    api, worker = 'mentra-rag-verify-api-' + suffix, 'mentra-rag-verify-worker-' + suffix
    frontend = 'mentra-rag-verify-frontend-' + suffix
    root = Path(__file__).resolve().parents[2]
    provider = ThreadingHTTPServer(('0.0.0.0', 18402), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    from app.core.config import settings
    if not settings.cloudinary_url: raise RuntimeError('Set CLOUDINARY_URL for the real private-file runtime check')
    env = dict(APP_ENV='test', CLOUDINARY_URL=settings.cloudinary_url, DATABASE_URL=f'postgresql://rag_test:rag_test_only@host.docker.internal:15438/{database}',
        QDRANT_URL='http://host.docker.internal:16335', QDRANT_API_KEY='test-only', QDRANT_COLLECTION=collection,
        AI_MODEL='rag-test', AI_BASE_URL='http://host.docker.internal:18402/v1', AI_API_KEY='test-only',
        FRONTEND_ORIGIN='http://127.0.0.1:15174', CORS_ORIGINS='http://127.0.0.1:15173,http://127.0.0.1:15174',
        RAG_RERANKER_PATH='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
    environment_directory=TemporaryDirectory(prefix='mentra-file-runtime-')
    environment_file=Path(environment_directory.name)/'runtime.env'
    environment_file.write_text(''.join(key+'='+value+'\n' for key,value in env.items()),encoding='utf-8')
    common = ['--env-file',str(environment_file),'-w','/app']
    report = dict(production_api=True, durable_worker=True, cloudinary_private_originals=True, real_embeddings=True,
        real_server_qdrant=True, chat_provider='local deterministic HTTP fixture', checks=[])
    client = httpx.Client(base_url='http://127.0.0.1:18401', headers={'Origin':'http://127.0.0.1:15173'}, timeout=30)
    try:
        docker('exec','mentra-rag-test-postgres','psql','-U','rag_test','-d','rag_test','-c',f'CREATE DATABASE {database}')
        docker('run','-d','--name',api,'-p','127.0.0.1:18401:8000',*common,'--entrypoint','sh',image,
            '-c','python -m app.db.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000')
        wait_ready(client); register(client)
        context = client.post('/api/v1/learning-contexts', json=dict(name='Python', activate=True)); context.raise_for_status()
        source_bytes = b'Python decorators wrap functions to add reusable behavior and logging.'
        staged=client.post('/api/v1/files/uploads',data=dict(purpose='library',operation_key=uuid4().hex),files={'file':('notes.txt',source_bytes,'text/plain')});staged.raise_for_status()
        upload=client.post('/api/v1/documents',json=dict(file_id=staged.json()['id'],title='Runtime notes',context_ids=[context.json()['context_id']],idempotency_key=uuid4().hex));upload.raise_for_status();accepted=upload.json()
        assert client.get('/api/v1/rag/jobs/'+accepted['job_id']).json()['state'] == 'QUEUED'
        report['checks'].append('upload survives while the worker is stopped')
        docker('run','-d','--name',worker,*common,'--entrypoint','python',image,'-m','app.rag.worker')
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = client.get('/api/v1/rag/jobs/'+accepted['job_id']).json()
            if job['state'] == 'SUCCEEDED': break
            if job['state'] == 'FAILED': raise RuntimeError(job['error'])
            time.sleep(0.5)
        assert job['state'] == 'SUCCEEDED', job
        report['checks'].append('separate production worker claims and publishes the durable upload')
        chat = client.post('/api/v1/chat', json=dict(messages=[dict(role='user',content='Explain decorators')], retrieval=dict(mode='SOURCE_SPECIFIC',document_ids=[accepted['document_id']]))); chat.raise_for_status()
        answer = chat.json(); assert answer['citations'] == ['S1']; source = answer['sources'][0]
        path = f"/api/v1/documents/{source['document_id']}/versions/{source['version_id']}/source"
        assert client.get(path).content == source_bytes
        report['checks'].append('real HTTP chat orchestration returns a resolvable authorized citation')
        docker('restart',api); wait_ready(client)
        assert client.get(path).content == source_bytes
        report['checks'].append('API restart preserves the session, source metadata and Cloudinary original bytes')
        docker('stop','--time','10',worker)
        doc = client.get('/api/v1/documents/'+accepted['document_id']).json()
        rebuilt = client.post(f"/api/v1/documents/{doc['id']}/reindex", json=dict(expected_revision=doc['revision'],idempotency_key=uuid4().hex)); rebuilt.raise_for_status()
        docker('start',worker)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = client.get('/api/v1/rag/jobs/'+rebuilt.json()['id']).json()
            if job['state'] == 'SUCCEEDED': break
            time.sleep(0.5)
        assert job['state'] == 'SUCCEEDED', job
        report['checks'].append('worker restart claims a queued reindex without losing the active source')
        other = httpx.Client(base_url=client.base_url, headers=client.headers, timeout=30)
        try:
            register(other)
            assert other.get(path).status_code == 404
        finally:
            other.close()
        report['checks'].append('another authenticated learner cannot fetch the original source bytes')
        client.delete('/api/v1/documents/'+doc['id']).raise_for_status()
        assert client.get(path).status_code == 404
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            remaining=docker('exec','mentra-rag-test-postgres','psql','-U','rag_test','-d',database,'-tAc',
                "SELECT count(*) FROM file_binding WHERE released_at IS NULL")
            if remaining.strip()=='0': break
            time.sleep(0.5)
        assert remaining.strip()=='0'
        report['checks'].append('deletion immediately excludes source access and releases original file bindings')
        docker('run','-d','--name',frontend,'-p','127.0.0.1:15174:8080','mentra-rag-frontend-verify:latest')
        browser = subprocess.run(['node', str(root / 'frontend/scripts/verify-rag-runtime.mjs')], capture_output=True, text=True, timeout=180)
        if browser.returncode:
            raise RuntimeError(browser.stderr)
        report['browser'] = json.loads(browser.stdout)
        print(json.dumps(report, indent=2))
    finally:
        client.close(); provider.shutdown(); provider.server_close()
        # This API points exclusively at this run's disposable database. Delete
        # its exact registered originals before removing their registry rows.
        docker('exec',api,'python','-c',
            'from sqlalchemy import update; from app.files.factory import create_files; '
            'from app.files.tables import assets, bindings; from app.files.service import now; '
            'files=create_files(); '
            'session=files.sessions(); '
            'session.execute(update(bindings).values(released_at=now())); '
            'session.execute(update(assets).values(expires_at=now(),lease_until=None,retry_at=None)); '
            'session.commit(); session.close(); '
            '[files.cleanup(limit=100) for _ in range(3)]; files.close()',check=False)
        environment_directory.cleanup()
        docker('rm','-f',frontend,worker,api,check=False)
        httpx.delete('http://127.0.0.1:16335/collections/'+collection, timeout=10)
        docker('exec','mentra-rag-test-postgres','psql','-U','rag_test','-d','rag_test','-c',f'DROP DATABASE IF EXISTS {database} WITH (FORCE)',check=False)


if __name__ == '__main__':
    main()
