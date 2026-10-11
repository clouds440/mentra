"""Deterministic external search double for browser tests only."""
import asyncio


class BrowserSearchProvider:
    async def search(self, request):
        await asyncio.sleep(1.5)
        return {'results': {'web': [
            dict(url='https://www.python.org/downloads/', title='Python release information',
                 description='Verified release information in a deterministic test fixture.', page_age='2026-10-08'),
            dict(url='https://docs.python.org/3/', title='Python documentation', description='Supporting documentation.'),
        ]}}

    async def close(self): pass
