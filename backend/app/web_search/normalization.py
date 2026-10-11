"""Bounded provenance normalization. Retrieval time never substitutes for source age."""
import re
from datetime import date, datetime, timezone
from .schemas import WebSource
from .urls import public_url, in_scope, favicon_url


def clean_text(value, limit):
    if not isinstance(value, str):
        return ''
    return ' '.join(re.sub(r'<[^>]*>', '', value).split())[:limit]


def source_date(value, now):
    if not isinstance(value, str) or not value:
        return {}
    raw = value[:100]
    fields = dict(date_raw=raw, date_origin='provider_reported', source_date_status='invalid')
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            day, instant = date.fromisoformat(raw), None
        else:
            parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            day = parsed.date()
            instant = parsed.astimezone(timezone.utc) if parsed.tzinfo else None
            if not parsed.tzinfo:
                fields['warnings'] = ['timezone_unavailable']
        fields.update(published_date=day, published_at=instant,
                      date_precision='datetime' if instant else 'date',
                      source_date_status='future' if (instant > now if instant else day > now.date()) else 'available')
    except (ValueError, OverflowError):
        pass
    return fields


def normalize_results(payload: dict, website: str | None, now: datetime) -> tuple[list[WebSource], bool]:
    sections = payload.get('results', {})
    if not isinstance(sections, dict):
        raise ValueError('Missing search result sections.')
    sources, seen, dropped = [], set(), False
    for kind in ('web', 'news'):
        rows = sections.get(kind, [])
        if not isinstance(rows, list):
            raise ValueError('Invalid result section.')
        for row in rows[:100]:
            if not isinstance(row, dict):
                dropped = True
                continue
            try:
                url, host = public_url(row.get('url', ''))
                if not in_scope(host, website):
                    dropped = True
                    continue
                if url in seen:
                    continue
                seen.add(url)
                snippets = row.get('snippets', [])
                excerpt = clean_text(' '.join(x for x in snippets[:4] if isinstance(x, str)), 1200) if isinstance(snippets, list) else ''
                excerpt = excerpt or clean_text(row.get('description'), 1200)
                sources.append(WebSource(url=url, domain=host, favicon_url=favicon_url(host),
                    title=clean_text(row.get('title'), 200) or host, excerpt=excerpt,
                    searched_at=now, **source_date(row.get('page_age'), now)))
                if len(sources) == 5:
                    return sources, dropped
            except (ValueError, TypeError):
                dropped = True
    return sources, dropped
