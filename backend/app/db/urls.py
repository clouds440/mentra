"""Provider-neutral PostgreSQL URL handling; preserve host, SSL and driver options."""

from sqlalchemy.engine import make_url, URL


def postgres_url(value: str) -> URL:
    if not value.strip():
        raise ValueError('DATABASE_URL is required')
    if value.startswith('postgres://'):
        value = 'postgresql://' + value[len('postgres://'):]
    url = make_url(value)
    if url.drivername not in ('postgresql', 'postgresql+psycopg'):
        raise ValueError('DATABASE_URL must use PostgreSQL (postgresql:// or postgresql+psycopg://)')
    return url.set(drivername='postgresql+psycopg')
