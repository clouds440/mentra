"""Bounded server-error deduplication without changing exception objects."""
from collections import OrderedDict
from threading import Lock
from time import monotonic
import logging

reported = OrderedDict()
lock = Lock()


def mark_reported(error):
    with lock:
        stamp = monotonic()
        reported[id(error)] = stamp
        while reported and (len(reported) > 1024 or next(iter(reported.values())) < stamp - 30):
            reported.popitem(last=False)


class ServerErrorFilter(logging.Filter):
    def filter(self, record):
        if record.name.startswith('uvicorn') and record.exc_info and record.exc_info[1]:
            with lock:
                stamp = reported.get(id(record.exc_info[1]))
                if stamp is not None and monotonic() - stamp < 30:
                    return False
        return True
