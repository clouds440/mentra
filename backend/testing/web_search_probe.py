"""Explicit manual live gate; never runs on startup or in routine tests."""
import asyncio
from datetime import datetime, timezone
from app.web_search.you_mcp import YouMCPProvider
from app.web_search import SearchInput
from app.web_search.normalization import normalize_results


async def main():
    provider = YouMCPProvider()
    try:
        async with asyncio.timeout(20):
            payload = await provider.search(SearchInput(query='Python latest release', website='python.org'))
            sources, dropped = normalize_results(payload, 'python.org', datetime.now(timezone.utc))
            print({'successful_free_call': True, 'protocol': provider.protocol, 'sources': len(sources), 'domains': list(dict.fromkeys(s.domain for s in sources)),
                'source_dates': [s.date_raw for s in sources], 'discarded': dropped})
    except Exception as error:
        print({'successful_free_call': False, 'error_type': type(error).__name__, 'outcome': getattr(error, 'outcome', 'timeout' if isinstance(error, TimeoutError) else 'unavailable')})
        raise SystemExit(1) from None
    finally:
        await provider.close()


if __name__ == '__main__':
    asyncio.run(main())
