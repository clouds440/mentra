"""Public hostname and URL validation; never fetch model-selected URLs."""
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit
import idna

_RESERVED = ('localhost', 'local', 'internal', 'test', 'invalid', 'example', 'onion')


def normalize_host(value: str) -> str:
    value = value.strip()
    parts = urlsplit(value if '://' in value else 'https://' + value)
    if parts.scheme not in ('https', 'http') or parts.username or parts.password or parts.port is not None:
        raise ValueError('Use a public website hostname or HTTP URL without credentials or a port.')
    host = idna.encode((parts.hostname or '').rstrip('.'), uts46=True).decode('ascii').lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('IP addresses are not website scopes.')
    if len(host) > 253 or '.' not in host or host.split('.')[-1].isdigit() or any(host == name or host.endswith('.' + name) for name in _RESERVED):
        raise ValueError('Use a public website hostname.')
    if not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.')):
        raise ValueError('Invalid website hostname.')
    return host


def normalize_query(query: str, website: str | None) -> tuple[str, str | None]:
    operators = list(re.finditer(r'(?i)(?<!\w)(-?site:)\S+', query))
    if operators:
        if len(operators) != 1 or operators[0].group(1).startswith('-') or re.search(r'(?i)\b(OR|AND|NOT)\b', query) or any(c in operators[0].group() for c in '\"\'()*'):
            raise ValueError('Use one positive website scope, without boolean site operators.')
        operator = operators[0]
        host = normalize_host(operator.group().split(':', 1)[1])
        if website and website != host:
            raise ValueError('The query website conflicts with the website argument.')
        website = website or host
        query = ' '.join((query[:operator.start()] + query[operator.end():]).split())
        if not query:
            raise ValueError('Provide a query in addition to the website.')
    return query, website


def public_url(value: str) -> tuple[str, str]:
    if len(value) > 2048:
        raise ValueError('URL is too long.')
    parts = urlsplit(value)
    if parts.scheme not in ('https', 'http'):
        raise ValueError('Unsupported link scheme.')
    host = normalize_host(value)
    if any(ord(c) < 32 for c in value):
        raise ValueError('Invalid URL.')
    return urlunsplit((parts.scheme, host, parts.path or '/', parts.query, '')), host


def in_scope(host: str, website: str | None) -> bool:
    return website is None or host == website or host.endswith('.' + website)


def favicon_url(host: str) -> str:
    # Direct HTTPS origin only: no query or private search terms sent to an icon aggregator.
    return f'https://{host}/favicon.ico'
