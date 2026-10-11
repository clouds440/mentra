"""Application composition; provider resources open only during a search."""
from .service import WebSearchService
from .repositories.postgres import UsageRepository


def create_web_search(sessions, config):
    from .you_mcp import YouMCPProvider
    return WebSearchService(YouMCPProvider(), UsageRepository(sessions,
        global_limit=config.web_search_daily_limit, user_limit=config.web_search_user_daily_limit,
        minute_limit=config.web_search_user_minute_limit), enabled=config.web_search_enabled,
        reference_timezone=config.web_search_timezone, cache_seconds=config.web_search_cache_seconds)
