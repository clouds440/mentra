"""Validate and normalize a model-selected personal event date."""

def normalize_candidate(candidate):
    """Canonicalize equivalent date/clock encodings without guessing DST folds."""
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo
    from .temporal import unique_local
    from app.core.exceptions import AppError
    if candidate is None or not candidate.timezone or not candidate.starts_at:
        return candidate
    try:
        zone = ZoneInfo(candidate.timezone)
        day = date.fromisoformat(candidate.local_date) if candidate.local_date else None
        def instant(value):
            if 'T' not in value and ' ' not in value:
                if day is None:
                    raise ValueError('A clock needs a date')
                clock = time.fromisoformat(value)
                if clock.tzinfo is not None:
                    raise ValueError('A standalone clock offset requires review')
                local = datetime.combine(day, clock)
            else:
                local = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return unique_local(local, candidate.timezone) if local.tzinfo is None else local
        start = instant(candidate.starts_at)
        if day is not None and start.astimezone(zone).date() != day:
            return candidate  # Conflicting dates remain reviewable.
        end = instant(candidate.ends_at) if candidate.ends_at else None
        return candidate.model_copy(update=dict(local_date=None, starts_at=start.isoformat(), ends_at=end.isoformat() if end else None))
    except (ValueError, KeyError, AppError):
        return candidate
