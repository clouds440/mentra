"""Read-only RFC 5545 export. Reminders and evidence never leave the inbox."""
from datetime import datetime, timedelta, timezone
from .schemas import EventRecord


def _text(value: str) -> str:
    return value.replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _fold(line: str) -> str:
    """Fold by UTF-8 octets without splitting a multibyte character."""
    parts, current, size = [], '', 0
    for character in line:
        width = len(character.encode('utf-8'))
        if size + width > 75:
            parts.append(current)
            current, size = ' ', 1
        current += character
        size += width
    return '\r\n'.join([*parts, current])


def calendar_file(event: EventRecord) -> bytes:
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Mentra//Events//EN', 'CALSCALE:GREGORIAN',
             'BEGIN:VEVENT', f'UID:{event.id}@mentra.local', f'SEQUENCE:{event.revision}',
             f'DTSTAMP:{_stamp(event.updated_at)}', f'LAST-MODIFIED:{_stamp(event.updated_at)}',
             f'SUMMARY:{_text(event.title)}', f'DESCRIPTION:{_text(event.description)}',
             'STATUS:CANCELLED' if event.status == 'cancelled' else 'STATUS:CONFIRMED']
    if event.local_date is not None:
        lines += [f'DTSTART;VALUE=DATE:{event.local_date:%Y%m%d}',
                  f'DTEND;VALUE=DATE:{event.local_date + timedelta(days=1):%Y%m%d}']
    else:
        lines.append(f'DTSTART:{_stamp(event.starts_at)}')
        if event.ends_at is not None:
            lines.append(f'DTEND:{_stamp(event.ends_at)}')
    lines += ['END:VEVENT', 'END:VCALENDAR']
    return ('\r\n'.join(_fold(line) for line in lines) + '\r\n').encode('utf-8')
