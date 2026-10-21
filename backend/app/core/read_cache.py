"""Conservative read keys and bounded, copy-isolated process-local reuse."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic
import re
import unicodedata


def normalized_query(value):
    value = unicodedata.normalize('NFC', value)
    # Preserve case, operators, quotations, code and line structure. Never
    # remove words, numbers, negation or punctuation to manufacture a hit.
    if '\n' not in value and '\r' not in value and not re.search(r'[^\w .,?!-]', value):
        value = re.sub(r' +', ' ', value).strip()
    return value


class ReadCache:
    def __init__(self, *, capacity=128, ttl=120, clock=monotonic):
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.entries = OrderedDict()
        self.lock = RLock()

    def get(self, key):
        with self.lock:
            item = self.entries.get(key)
            if item is None:
                return None
            if item[0] is not None and self.clock() >= item[0]:
                self.entries.pop(key, None)
                return None
            self.entries.move_to_end(key)
            return deepcopy(item[1])

    def put(self, key, value):
        with self.lock:
            now = self.clock()
            for expired in [k for k, (deadline, _) in self.entries.items() if deadline is not None and deadline <= now]:
                self.entries.pop(expired, None)
            self.entries[key] = (now + self.ttl if self.ttl is not None else None, deepcopy(value))
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
