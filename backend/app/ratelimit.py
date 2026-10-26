import threading
import time
from collections import deque


class SlidingWindowLimiter:
    """In-memory, per-process: at most `limit` hits per key in any `window` seconds.
    Fine for a single uvicorn worker; with several, each enforces its own cap."""

    def __init__(self, limit: int, window: float, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Record an attempt. Returns None if allowed, else seconds until a slot frees up."""
        now = self._clock()
        with self._lock:
            if len(self._hits) > 10_000:  # keys are client-chosen PINs; don't let them pile up
                for k in [k for k, d in self._hits.items() if d[-1] <= now - self.window]:
                    del self._hits[k]
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window - now
            hits.append(now)
            return None
