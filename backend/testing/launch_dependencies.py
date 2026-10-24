"""HTTP acceptance while the operator stops/starts only disposable dependencies."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import httpx


def main(expected):
    base = os.environ['TEST_API_URL']
    if urlsplit(base).hostname != 'mentra-launchgate-api':
        raise RuntimeError('Dependency checks require the explicitly named disposable API')
    account = json.loads(Path('/tmp/launchgate-accounts.json').read_text())[0]
    with httpx.Client(base_url=base, timeout=15) as client:
        ready = client.get('/api/v1/health/ready')
        identity = client.get('/api/v1/auth/me', headers=account['headers'])
        if expected == 'database-down':
            assert ready.status_code == 503
            assert identity.status_code == 503
            assert identity.json()['error']['code'] == 'DATABASE_BUSY'
        elif expected == 'qdrant-down':
            assert ready.status_code == 503
            assert identity.status_code == 200
        else:
            assert ready.status_code == identity.status_code == 200
        print(json.dumps(dict(expected=expected, readiness=ready.status_code, authenticated=identity.status_code)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected', choices=['database-down','qdrant-down','recovered'])
    main(parser.parse_args().expected)
