"""Markdown-aware W citation extraction and historical prompt projection."""
import re
from markdown_it import MarkdownIt


def historical_web_markers(content: str) -> str:
    # Canonical messages are untouched. Only their prompt projection is renamed.
    return re.sub(r'\[\[(W\d+)\]\]', r'[historical web reference \1]', content)


def edit_web_links(content, metadata):
    """Reuse validated historical URLs for an edit, without claiming a new search."""
    from .schemas import WebSource
    try:
        sources={source.token:source for source in (WebSource.model_validate(value) for value in metadata.get('web_sources', []))}
    except (ValueError, TypeError):
        return None
    tokens=set(re.findall(r'\[\[(W\d+)\]\]', content))
    if tokens - sources.keys():
        return None
    def link(match):
        source=sources[match[1]]
        url=source.url.replace('>', '%3E')
        return f'[Source {source.token}](<{url}>)'
    return re.sub(r'\[\[(W\d+)\]\]', link, content)


def web_citations(content: str, valid: set[str]) -> list[str]:
    # Protect escaped brackets before parsing; CommonMark otherwise decodes them
    # into plain text indistinguishable from active markers.
    content = re.sub(r'(?<!\\)\\\[\[W\d+\]\]|\\\[\\\[W\d+\\\]\\\]', 'escaped web marker', content)
    result = []
    for token in MarkdownIt('commonmark').parse(content):
        if token.type != 'inline':
            continue
        link_depth = 0
        for child in token.children or []:
            if child.type == 'link_open':
                link_depth += 1
            elif child.type == 'link_close':
                link_depth -= 1
            elif child.type == 'text' and not link_depth:
                for marker in re.findall(r'\[\[(W\d+)\]\]', child.content):
                    if marker in valid and marker not in result:
                        result.append(marker)
    return result
