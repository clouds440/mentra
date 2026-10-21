"""Reject provider control markup returned as ordinary assistant text."""
import re


_TOOL_MARKUP = re.compile(r'^\s*<[/]?[|｜]+\s*DSML[|｜]+\s*(?:calls|function_calls|invoke|parameter)\b')


class ProviderProtocolError(ValueError):
    pass


def raw_tool_markup(content):
    return isinstance(content, str) and bool(_TOOL_MARKUP.match(content))


def validate_response(message):
    if not getattr(message, 'tool_calls', None) and raw_tool_markup(getattr(message, 'content', None)):
        raise ProviderProtocolError('Provider returned tool-control markup as answer text')
    return message
