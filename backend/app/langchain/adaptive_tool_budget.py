"""Grow working allowances from measured context headroom, never permissions."""
from app.core.logging import workflow_logger


def rebalance_tools(budget, *, used_tokens, input_limit, recovery_limit, envelope):
    tokens_left = budget.max_result_tokens - budget.result_tokens
    bytes_left = budget.max_result_bytes - budget.result_characters
    needs_results = tokens_left < 1200 or bytes_left < 4800
    time_available = not envelope or envelope.remaining > envelope.answer_reserve + 5
    if needs_results and time_available:
        # Transcript/tool schemas are counted together. Keep protocol/final-answer
        # input space; the configured output reserve is already excluded upstream.
        if input_limit - used_tokens - 1024 < 1200:
            input_limit = max(input_limit, recovery_limit)
        room = max(0, input_limit - used_tokens - 1024)
        if room >= 600:
            previous = budget.max_result_tokens
            budget.max_result_tokens = max(previous, budget.result_tokens + room)
            budget.max_result_bytes = max(budget.max_result_bytes, budget.result_characters + room * 4)
            if budget.max_result_tokens > previous:
                workflow_logger.event('tool.budget_expanded', kind='results', input_limit=input_limit,
                    result_tokens=budget.max_result_tokens, context_headroom=room)
    # More physical reads are allowed when the model keeps asking for new work.
    # Duplicate reads remain cached; writes retain their independent two-write fence.
    if budget.calls >= budget.max_calls and budget.max_calls in (6, 9) and time_available and budget.max_result_tokens - budget.result_tokens >= 600:
        budget.max_calls = min(12, budget.max_calls + 3)
        workflow_logger.event('tool.budget_expanded', kind='calls', max_calls=budget.max_calls)
    return input_limit
