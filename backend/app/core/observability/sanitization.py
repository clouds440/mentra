"""Explicitly selected operational metadata only. Never stringify domain objects."""
import math

BLOCKED = ('password', 'secret', 'token', 'cookie', 'authorization', 'content', 'prompt', 'answer', 'grade', 'url', 'key', 'text', 'quote', 'filename', 'data', 'message')
SAFE_FIELDS = {'prompt_source', 'prompt_version', 'token_count', 'input_token_count', 'output_token_count', 'context_count', 'max_concepts', 'metadata_unavailable'}


def safe_metadata(value, depth=0):
    if depth > 3:
        return None
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else None
    if type(value) is str:
        return ''.join(c if c.isprintable() else '?' for c in value[:240])
    if type(value) is dict:
        return {k[:80]: safe_metadata(v, depth+1) for k, v in list(value.items())[:30]
                if type(k) is str and (k in SAFE_FIELDS or not any(part in k.lower() for part in BLOCKED))}
    if type(value) in (list, tuple):
        return [safe_metadata(x, depth+1) for x in value[:30]]
    return None


def error_metadata(error):
    import re
    frames, trace = [], error.__traceback__
    while trace and len(frames) < 20:
        frames.append(dict(file=trace.tb_frame.f_code.co_filename.replace('\\', '/').split('/')[-1],
                           function=trace.tb_frame.f_code.co_name, line=trace.tb_lineno))
        trace = trace.tb_next
    value = dict(type=type(error).__name__, frames=frames)
    try:
        reason = 'Operation failed; inspect exception type and code.'
        if type(error).__name__.endswith('ValidationError') and callable(getattr(error,'errors',None)):
            details=error.errors()
            known = {'body', 'query', 'path', 'answers', 'questions', 'expected_revision', 'client_request_id',
                     'title', 'content', 'concept_ids', 'context_ids', 'password', 'username', 'token'}
            value['validation']=[dict(location=[part if isinstance(part, int) or part in known else 'field'
                for part in item.get('loc', [])], type=item.get('type'), reason='Validation failed.') for item in details[:10]]
            reason='Input validation failed; see field locations and validation types.'
        if type(error).__module__.startswith(('sqlalchemy', 'psycopg')):
            reason = 'Database operation failed; inspect exception type and SQLSTATE.'
        value['reason'] = reason
    except Exception:
        value['reason'] = 'Exception message unavailable.'
    status = getattr(error, 'status_code', None)
    if isinstance(status, int) and 100 <= status <= 599:
        value['http_status'] = status
    code = getattr(error, 'code', None)
    if isinstance(code, str) and re.fullmatch('[A-Z][A-Z0-9_]{0,79}', code):
        value['code'] = code
    origin = getattr(error, 'orig', None)
    sqlstate = getattr(origin, 'sqlstate', None) or getattr(origin, 'pgcode', None)
    if isinstance(sqlstate,str) and re.fullmatch('[A-Z0-9]{5}',sqlstate):
        value['sqlstate'] = sqlstate
    cause = error.__cause__ or (error.__context__ if not error.__suppress_context__ else None)
    if cause is not None and cause is not error:
        try:
            value['cause'] = dict(type=type(cause).__name__)
        except Exception:
            value['cause'] = dict(type=type(cause).__name__)
    return value
