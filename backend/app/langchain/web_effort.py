"""Quick lookup is a phase, not an invitation to consume the workflow ceiling."""


def search_phase(scope):
    calls = scope.get('_web_physical_calls', 0)
    cached = list(scope.get('_web_cache', {}).values())
    terminal = any(result.get('outcome') in ('quota_exhausted', 'rate_limited', 'disabled') for result in cached)
    extended = scope.get('_web_effort') == 'extended'
    # Recover automatically from an empty/failed initial batch, but do not launch
    # an oversized parallel batch while its first results are still in flight.
    empty_batch = len(cached) >= 2 and not scope.get('web_sources') and not any(result.get('sources') for result in cached)
    allowance = 4 if empty_batch else 2
    closed = terminal or not extended and calls >= allowance
    return dict(mode='extended' if extended else 'quick', closed=closed,
        reason='provider_allowance' if terminal else 'quick_lookup_complete' if closed else None,
        calls_remaining=0 if closed else None if extended else max(0, allowance-calls))
