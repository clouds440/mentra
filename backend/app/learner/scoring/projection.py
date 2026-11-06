"""Exact exponential sufficient statistics for the current bounded predictor.

No evidence is discarded: this is a replaceable ranking index, never a belief
or an evidence ledger. It is valid only at/after its source timestamp.
"""
from datetime import datetime
from math import isfinite
from .retention import observation_freshness
from .signals import difficulty_band

BANDS = ('easy', 'medium', 'hard')


def project(state, half_life_days):
    if not isfinite(half_life_days) or half_life_days <= 0:
        raise ValueError('Positive finite half life required')
    data = state.policy_data
    dates = [value for value in (state.last_evidence_at, state.last_demonstrated_at) if value]
    for band in BANDS:
        dates.extend(datetime.fromisoformat(row['at']) for row in data.get(f'{band}_observations', []))
        if data.get(f'{band}_last_at'):
            dates.append(datetime.fromisoformat(data[f'{band}_last_at']))
    if not dates:
        return None
    anchor = max(dates)
    result = dict(anchor=anchor, independent_items=len(data.get('independent_items', [])),
                  base_half_life=half_life_days,
                  policy_identity=data.get('policy_identity', state.mastery_policy_version))
    result.update({key:getattr(state,key) for key in ('mastery','estimate_confidence','retention_confidence',
        'last_demonstrated_at','verification_required','mastery_policy_version','retention_policy_version')})
    for band in BANDS:
        weight = data.get(f'{band}_weight', 0)
        days = len(data.get(f'{band}_recall_times', data.get('recall_days', [])))
        result[f'{band}_half_life'] = half_life_days * (1 + max(0, days - 1) * .3)
        result[f'{band}_supported'] = weight >= 2 and len(data.get(f'{band}_items', [])) >= 3
        rows = data.get(f'{band}_observations')
        if rows:
            amplitude = sum(row['weight'] * (row['outcome'] - .5) * observation_freshness(
                state, datetime.fromisoformat(row['at']), anchor, half_life_days, band) for row in rows) / (1 + weight)
        else:
            last = data.get(f'{band}_last_at')
            amplitude = (((.5 + data.get(f'{band}_success', 0)) / (1 + weight)) - .5) * (
                observation_freshness(state, datetime.fromisoformat(last), anchor, half_life_days, band) if last else 0)
        result[f'{band}_amplitude'] = amplitude
    result['retention_half_life'] = result[f"{difficulty_band(data.get('anchor_difficulty', .5))}_half_life"]
    return result


def expected(projection, difficulty, now):
    if now < projection['anchor']:
        raise ValueError('Projection cannot predict before its source')
    band = difficulty_band(difficulty)
    if not projection[f'{band}_supported']:
        return .5, False
    age = (now - projection['anchor']).total_seconds() / 86400
    return .5 + projection[f'{band}_amplitude'] * 2 ** (-age / projection[f'{band}_half_life']), True
