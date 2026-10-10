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
    code = getattr(error, 'code', None)
    if isinstance(code, str) and re.fullmatch('[A-Z][A-Z0-9_]{0,79}', code):
        value['code'] = code
    return value
