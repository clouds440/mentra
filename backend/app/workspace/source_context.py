"""Resolve explicitly attached public pages through the same transport as Reader."""
import asyncio

from app.web_search.preview import read_publisher


async def resolve_source_context(annotations, current_message_id):
    pages = dict.fromkeys(item['source']['url'] for item in annotations
                         if item.get('mode') == 'page' and item['message_id'] == current_message_id)
    if not pages:
        return annotations
    # Keep publisher I/O bounded and share the prompt budget across pages.
    readers = await asyncio.gather(*(read_publisher(url) for url in pages), return_exceptions=True)
    char_limit = 6000 // len(pages)
    excerpts = {}
    for url, reader in zip(pages, readers):
        if isinstance(reader, dict) and reader['blocks']:
            text = '\n\n'.join(reader['blocks'])
            excerpts[url] = dict(status='readable', resolved_url=reader['url'], text=text[:char_limit],
                                 sample_limited=len(text) > char_limit)
        else:
            excerpts[url] = dict(status='unavailable')
    return [dict(item, **excerpts[item['source']['url']])
            if item.get('mode') == 'page' and item['message_id'] == current_message_id else item
            for item in annotations]
