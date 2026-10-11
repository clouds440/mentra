"""Run checks against the existing local test container, never the app database."""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote


def main():
    container = 'mentra-rag-test-postgres'
    info = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]
    if info['Config']['Image'] != 'postgres:17':
        raise RuntimeError('Unexpected test database image')
    ports = info['NetworkSettings']['Ports']['5432/tcp']
    if not any(port['HostIp'] == '127.0.0.1' and port['HostPort'] == '15438' for port in ports):
        raise RuntimeError('Unexpected test database binding')
    configured = dict(entry.split('=', 1) for entry in info['Config']['Env'] if '=' in entry)
    environment = dict(os.environ)
    environment['TEST_DATABASE_URL'] = 'postgresql://' + quote(configured.get('POSTGRES_USER', 'postgres'), safe='') + ':' + quote(configured['POSTGRES_PASSWORD'], safe='') + '@127.0.0.1:15438/' + quote(configured.get('POSTGRES_DB', 'postgres'), safe='')
    backend = Path(__file__).resolve().parents[1]
    if sys.argv[1:2] == ['--browser']:
        return subprocess.call(['npm.cmd', 'run', 'test:e2e', '--', *sys.argv[2:]], cwd=backend.parent / 'frontend', env=environment)
    command = sys.argv[1:] or ['-m', 'unittest', 'discover', '-s', 'tests', '-q']
    return subprocess.call([sys.executable, *command], cwd=backend, env=environment)


if __name__ == '__main__':
    raise SystemExit(main())
