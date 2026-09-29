import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict


class SlidingWindowLimiter:
    """Process-local sliding-window limiter.

    Good enough for brute-force protection on a single API process. Behind several replicas,
    move this to Redis or enforce it at the ingress.
    """

    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> bool:
        """Record an event for key. Returns False when the key is over its limit."""
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window_seconds:
                events.popleft()
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
