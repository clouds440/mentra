"""Killable extraction process, shared by every document-reading consumer."""
import json
import os
import signal
import subprocess
import sys
from app.documents.errors import DocumentReadError


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def read_isolated(path, kind, max_pages, timeout):
    process = subprocess.Popen([sys.executable, '-m', 'app.documents.worker', str(path), kind, str(max_pages)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=os.name != 'nt')
    try:
        output, _error = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name != 'nt':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
            if process.poll() is None:
                process.kill()
        process.communicate()
        raise DocumentReadError('Parsing exceeded the time limit. Split the material into smaller files.') from exc
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError) as exc:
        raise DocumentReadError('The file could not be parsed. Check it and upload an unlocked, valid copy.') from exc
    if process.returncode:
        error = result.get('error') if isinstance(result, dict) else None
        raise DocumentReadError(error or 'The file could not be parsed. Check it and upload an unlocked, valid copy.')
    if not isinstance(result, dict) or not isinstance(result.get('blocks'), list) or not isinstance(result.get('warnings'), list):
        raise DocumentReadError('The document reader returned invalid content.')
    return result
