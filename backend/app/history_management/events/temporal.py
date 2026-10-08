"""Explicit local dates and UTC instants. Never consult the host timezone."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from app.core.exceptions import AppError

UTC = timezone.utc


def local_choices(local: datetime, zone: str) -> list[datetime]:
    """Round-trip both folds: gaps have no choices, folds have two."""
    tz = ZoneInfo(zone)
    result = set()
    for fold in (0, 1):
        instant = local.replace(tzinfo=tz, fold=fold).astimezone(UTC)
        if instant.astimezone(tz).replace(tzinfo=None) == local:
            result.add(instant)
    return sorted(result)


def unique_local(local, zone):
    choices = local_choices(local, zone)
    if len(choices) != 1:
        raise AppError('DATE_AMBIGUOUS', 'This local time is skipped or repeated. Choose an explicit delivery instant.', 422)
    return choices[0]


def civil_start(day, zone):
    local = datetime.combine(day, time.min)
    for minute in range(1441):
        choices = local_choices(local + timedelta(minutes=minute), zone)
        if choices:
            if minute:
                # Historical IANA transitions can end a midnight gap between
                # minute boundaries (Monrovia 1972 ends at 00:44:30).
                previous = local + timedelta(minutes=minute-1)
                for second in range(1, 60):
                    candidate = previous + timedelta(seconds=second)
                    exact = local_choices(candidate, zone)
                    if exact:
                        return exact[0]
            if minute < 1440:
                return choices[0]
            break
    raise AppError('DATE_AMBIGUOUS', 'This civil date does not exist in the selected timezone.', 422)


def bounds(draft):
    if draft.local_date is not None:
        # A skipped civil date (e.g. Pacific/Apia 2011-12-30) is unusable.
        start = civil_start(draft.local_date, draft.timezone)
        try:
            cutoff = civil_start(draft.local_date + timedelta(days=1), draft.timezone)
        except AppError:
            cutoff = civil_start(draft.local_date + timedelta(days=2), draft.timezone)
        return start, cutoff
    start = draft.starts_at.astimezone(UTC)
    end = draft.ends_at.astimezone(UTC) if draft.ends_at else start
    return start, end


def reminder_due(draft, preferences, now):
    start, cutoff = bounds(draft)
    rule = draft.reminder
    if rule.mode == 'disabled':
        return None, 'cancelled'
    boundary = cutoff if draft.local_date is not None else start
    # An unused historical default is not a reason to reject a valid past
    # academic date (its former reminder time may have fallen in a DST gap).
    if rule.mode == 'default' and draft.local_date is not None and now >= boundary:
        return None, 'skipped'
    if rule.mode == 'at':
        due = rule.at.astimezone(UTC)
    elif draft.local_date is not None:
        local = datetime.combine(draft.local_date - timedelta(days=preferences['date_days_before']),
                                 time(preferences['date_hour'], preferences['date_minute']))
        due = unique_local(local, draft.timezone)
    else:
        due = start - timedelta(minutes=preferences['timed_offset_minutes'])
    # Timed reminders cannot arrive after the occurrence has started. Date-only
    # reminders may arrive during the local day, until its exclusive cutoff.
    if due >= boundary:
        raise AppError('INVALID_REMINDER', 'The reminder must precede the event cutoff.', 422)
    if now >= boundary:
        return due, 'skipped'
    if not preferences['reminders_enabled'] and due <= now:
        return due, 'skipped'
    return max(due, now), 'pending'


def bucket(row, now):
    if row['status'] != 'scheduled':
        return row['status']
    if row['kind'] in ('assignment', 'deadline'):
        return 'overdue' if now >= row['cutoff_at'] else 'upcoming'
    if row['local_date'] is not None:
        if now < row['sort_at']:
            return 'upcoming'
        return 'in_progress' if now < row['cutoff_at'] else 'past'
    if now < row['starts_at']:
        return 'upcoming'
    return 'in_progress' if row['ends_at'] and now < row['ends_at'] else 'past'


def preview(body, preferences=None, now=None):
    starts = local_choices(body.local_start, body.timezone) if body.local_start else []
    ends = local_choices(body.local_end, body.timezone) if body.local_end else []
    result = dict(timezone=body.timezone, local_date=body.local_date,
                start_choices=starts, end_choices=ends,
                requires_choice=(body.local_start is not None and len(starts) != 1)
                or (body.local_end is not None and len(ends) != 1), choices=[], field_errors=[])
    if preferences is None:
        return result
    from .schemas import EventDraft
    for field, local, choices in [('local_start', body.local_start, starts), ('local_end', body.local_end, ends)]:
        if local is not None and not choices:
            result['field_errors'].append(dict(field=field, code='DATE_AMBIGUOUS', message='This local time does not exist. Choose another time.'))
    if result['field_errors']:
        return result
    valid_pairs = [(start, end) for start in starts or [None] for end in ends or [None]
                   if end is None or end > start]
    if not valid_pairs:
        result['field_errors'].append(dict(field='local_end', code='INVALID_DATE', message='End must follow start.'))
        return result
    for start, end in valid_pairs:
        draft = EventDraft(title='Temporal preview', timezone=body.timezone, local_date=body.local_date,
                           starts_at=start, ends_at=end, reminder=body.reminder)
        try:
            bounds(draft)
        except AppError as error:
            result['field_errors'].append(dict(field='local_date', code=error.code, message=error.message))
            continue
        try:
            due, state = reminder_due(draft, preferences, now)
            result['choices'].append(dict(starts_at=start, ends_at=end, reminder_due_at=due, reminder_state=state))
        except AppError as error:
            issue = dict(field='reminder', code=error.code, message=error.message)
            if issue not in result['field_errors']:
                result['field_errors'].append(issue)
    return result
