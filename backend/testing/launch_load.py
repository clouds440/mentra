"""Bounded HTTP integration/load drill; no unit framework or external AI calls.

Requires an isolated production API at TEST_API_URL, a private fault fixture at
TEST_PROVIDER_URL, and explicit TEST_DATABASE_URL pointing to mentra_launchgate.
Run: python -m testing.launch_load --seconds 6 --concurrency 1 2 4 8
Writes only synthetic users to the explicitly fenced disposable database.
"""
import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import psycopg


def percentile(values, quantile):
    return round(sorted(values)[max(0, int(len(values) * quantile + .999) - 1)], 2)


async def main(args):
    database = urlsplit(os.environ['TEST_DATABASE_URL'])
    base, provider = os.environ['TEST_API_URL'], os.environ['TEST_PROVIDER_URL']
    if (database.hostname != 'mentra-launchgate-postgres' or database.path != '/mentra_launchgate'
            or os.environ.get('DATABASE_URL') != os.environ['TEST_DATABASE_URL']
            or urlsplit(base).hostname != 'mentra-launchgate-api'
            or urlsplit(provider).hostname != 'mentra-launchgate-provider'):
        raise RuntimeError('This drill accepts only its explicitly named disposable network/services')
    report = dict(stages=[], external_ai_calls=0, fixture='private deterministic OpenAI HTTP server')
    async with httpx.AsyncClient(base_url=base, timeout=45) as client, httpx.AsyncClient(base_url=provider, timeout=10) as fault:
        accounts = json.loads(Path(args.state).read_text()) if args.reuse else []
        for number in range(0 if args.reuse else 4):
            response = await client.post('/api/v1/auth/register', json=dict(username='launch_' + uuid4().hex[:16], password='Synthetic-only-password-2026!'))
            response.raise_for_status()
            account = response.json()
            headers = dict(Authorization='Bearer ' + account['access_token'])
            profile = await client.get('/api/v1/student-profile', headers=headers)
            response = await client.put('/api/v1/student-profile/details', headers=headers, json=dict(expected_version=profile.json()['version'], details=dict(education_level='undergraduate', field_of_study='Computing', learning_goal='Learn Python decorators safely', learning_preference='balanced', explanation_depth='standard')))
            response.raise_for_status()
            response = await client.post('/api/v1/student-profile/calibration/skip', headers=headers, json=dict(expected_version=response.json()['version']))
            response.raise_for_status()
            accounts.append(dict(identity=account, headers=headers))
        # Stable paginated, owner-specific records; the other account must not see them.
        for number, account in enumerate([] if args.reuse else accounts):
            for item in range(3):
                response = await client.post('/api/v1/learning-contexts', headers=account['headers'], json=dict(name=f'Launch owner {number} context {item}', activate=True))
                response.raise_for_status()
                account.setdefault('contexts', []).append(response.json()['context_id'])
        monitor = await psycopg.AsyncConnection.connect(os.environ['TEST_DATABASE_URL'], autocommit=True)
        samples = []

        async def sample_database():
            while True:
                cursor = await monitor.execute("SELECT count(*),count(*) FILTER (WHERE state='active') FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid()")
                samples.append(await cursor.fetchone())
                await asyncio.sleep(.1)

        monitoring = asyncio.create_task(sample_database())
        for concurrency in args.concurrency:
            timings, statuses = [], Counter()
            started = time.perf_counter()
            deadline = started + args.seconds

            async def requests(worker):
                count = 0
                while time.perf_counter() < deadline:
                    account = accounts[(worker + count) % len(accounts)]
                    path = ['/api/v1/auth/me', '/api/v1/conversations?limit=100', '/api/v1/learning-contexts?offset=0&limit=2', '/api/v1/documents/page?limit=100'][count % 4]
                    before = time.perf_counter()
                    response = await client.get(path, headers=account['headers'])
                    timings.append((time.perf_counter() - before) * 1000)
                    statuses[response.status_code] += 1
                    if response.status_code == 200 and path == '/api/v1/auth/me':
                        assert response.json()['learner_id'] == account['identity']['learner_id']
                    if response.status_code == 200 and path.startswith('/api/v1/learning-contexts'):
                        assert all(item['context_id'] in account['contexts'] for item in response.json())
                    count += 1
                    if sum(statuses.values()) >= 2000:
                        break

            await asyncio.gather(*(requests(worker) for worker in range(concurrency)))
            elapsed = time.perf_counter() - started
            errors = sum(count for status, count in statuses.items() if status != 200)
            report['stages'].append(dict(concurrency=concurrency, duration_s=round(elapsed, 2), requests=len(timings), requests_per_second=round(len(timings)/elapsed, 2), p50_ms=percentile(timings,.5), p95_ms=percentile(timings,.95), p99_ms=percentile(timings,.99), errors=errors, statuses=dict(statuses)))
            if errors / len(timings) > .05 or percentile(timings,.95) > 5000:
                raise RuntimeError('Load safety threshold reached: >5% errors or p95 >5s')
        monitoring.cancel()
        try:
            await monitoring
        except asyncio.CancelledError:
            pass
        await monitor.close()
        report['database'] = dict(samples=len(samples), peak_connections_excluding_monitor=max(value[0] for value in samples), peak_active_excluding_monitor=max(value[1] for value in samples), api_pool_size=5, overflow=0)
        if args.reuse:
            print(json.dumps(report, indent=2))
            return
        # Two real storage writes only; ingestion uses real local embeddings/Qdrant.
        for number, account in enumerate(accounts[:2]):
            data = (f'Owner {number}: Python decorators wrap functions to add reusable behavior.\n' * 100).encode()
            response = await client.post('/api/v1/files/uploads', headers=account['headers'], data=dict(purpose='library', operation_key=str(uuid4())), files=dict(file=(f'launch-{number}.txt', data, 'text/plain')))
            response.raise_for_status()
            account['file'] = response.json()
            response = await client.post('/api/v1/documents', headers=account['headers'], json=dict(file_id=account['file']['id'], title=f'Owner {number} decorators', context_ids=[account['contexts'][0]], idempotency_key=str(uuid4())))
            response.raise_for_status()
            account['document'] = response.json()
        for account in accounts[:2]:
            for _ in range(90):
                response = await client.get('/api/v1/rag/jobs/' + account['document']['job_id'], headers=account['headers'])
                response.raise_for_status()
                if response.json()['state'] == 'SUCCEEDED':
                    break
                if response.json()['state'] == 'FAILED':
                    raise RuntimeError('Synthetic ingestion failed: ' + str(response.json()))
                await asyncio.sleep(1)
            else:
                raise RuntimeError('Synthetic ingestion exceeded 90 seconds')
            response = await client.post('/api/v1/rag/search', headers=account['headers'], json=dict(query='What do Python decorators do?', mode='SOURCE_SPECIFIC', document_ids=[account['document']['document_id']]))
            response.raise_for_status()
            assert response.json()['chunks']
        denied = await client.get('/api/v1/documents/' + accounts[0]['document']['document_id'], headers=accounts[1]['headers'])
        assert denied.status_code == 404
        report['ingestion'] = dict(documents=2, originals='real Cloudinary', embeddings='real CPU E5', vector='real isolated Qdrant', cross_owner_denial=denied.status_code)
        # Permitted maximum text, then concurrent model operations through the API.
        async def chat(account, content='Hello, what is a Python decorator?'):
            response = await client.post('/api/v1/conversations/turns', headers=account['headers'], json=dict(conversation_id=str(uuid4()), client_turn_id=str(uuid4()), expected_revision=0, content=content))
            response.raise_for_status()
            return response.json()
        before = time.perf_counter()
        replies = await asyncio.gather(*(chat(account, 'a' * 4000 if number == 0 else 'Hello!') for number, account in enumerate(accounts)))
        report['chat'] = dict(concurrency=4, duration_s=round(time.perf_counter()-before,2), states=[item['turn']['state'] for item in replies])
        assert all(item['turn']['state'] == 'SUCCEEDED' for item in replies)
        oversize = await client.post('/api/v1/conversations/turns', headers=accounts[0]['headers'], content=b'x'*(2*1024*1024+1))
        assert oversize.status_code == 413
        report['body_limit'] = oversize.status_code
        await fault.post('/control', json=dict(mode='slow'))
        account = accounts[0]
        cid, tid = str(uuid4()), str(uuid4())
        response = await client.post('/api/v1/conversations/turns?stream=true', headers=account['headers'], json=dict(conversation_id=cid, client_turn_id=tid, expected_revision=0, content='Hello!'))
        response.raise_for_status()
        await asyncio.sleep(.3)
        stopped = await client.post(f'/api/v1/conversations/{cid}/turns/{tid}/stop', headers=account['headers'], json=dict(attempt=1))
        stopped.raise_for_status()
        assert stopped.json()['turn']['state'] == 'FAILED'
        assert stopped.json()['turn']['error'] == 'Response stopped.'
        report['stop'] = dict(state=stopped.json()['turn']['state'], stopped_notice=stopped.json()['turn']['error'] == 'Response stopped.')
        await fault.post('/control', json=dict(mode='ok'))
        report['provider_metrics'] = (await fault.get('/metrics')).json()
        Path(args.state).write_text(json.dumps(accounts))
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=6, choices=range(1,31))
    parser.add_argument('--concurrency', type=int, nargs='+', default=[1,2,4,8], choices=range(1,17))
    parser.add_argument('--state', default='/tmp/launchgate-accounts.json', help='Private disposable account state; delete after recovery drill')
    parser.add_argument('--reuse', action='store_true', help='Reuse the private synthetic state for read-only capacity sampling; no uploads/model calls')
    asyncio.run(main(parser.parse_args()))
