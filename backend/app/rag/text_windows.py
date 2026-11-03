"""Exact, bounded tokenizer windows shared by local inference consumers."""


def token_windows(text, count, limit, *, max_windows=8):
    if not text:
        return []
    windows, start = [], 0
    while start < len(text):
        if len(windows) >= max_windows:
            raise ValueError('Input exceeds bounded window coverage.')
        low, high = 0, len(text) - start
        while low < high:
            mid = (low + high + 1) // 2
            if count(text[start:start + mid]) <= limit:
                low = mid
            else:
                high = mid - 1
        if low == 0:
            raise ValueError('A source character exceeds the token budget.')
        part = text[start:start + low]
        if count(part) > limit:
            raise ValueError('Window exceeds exact token budget.')
        windows.append(part)
        start += low
    return windows
