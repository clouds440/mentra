"""Linux process-tree RSS sampling; excludes separate database/vector services."""
import os
from pathlib import Path
from threading import Event, Thread


class ProcessResources:
    def __init__(self):
        self.stop = Event()
        self.peak_mib = 0
        self.thread = Thread(target=self.sample, daemon=True)

    def rss(self, pid):
        try:
            status = Path(f'/proc/{pid}/status').read_text()
            own = next(int(line.split()[1]) for line in status.splitlines() if line.startswith('VmRSS:'))
            children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
            return own + sum(self.rss(child) for child in children)
        except (OSError, StopIteration, ValueError):
            return 0

    def sample(self):
        while not self.stop.is_set():
            self.peak_mib = max(self.peak_mib, self.rss(os.getpid()) / 1024)
            self.stop.wait(.1)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=1)
