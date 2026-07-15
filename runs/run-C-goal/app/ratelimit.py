"""In-memory sliding-window rate limiter, keyed by API key id.

The window is a true sliding 60-second window: we keep the timestamps of recent
requests per key and drop any older than 60s on each check. Rate-limit state is
intentionally in-memory (ephemeral) — the only durable state is the SQLite file.
"""
import math
import os
import time
from collections import defaultdict, deque

WINDOW_SECONDS = 60


def limit_per_minute() -> int:
    raw = os.environ.get("RATE_LIMIT_PER_MINUTE")
    if raw is None or raw == "":
        return 60
    try:
        value = int(raw)
    except ValueError:
        return 60
    return value if value > 0 else 60


class RateLimiter:
    def __init__(self):
        self._hits = defaultdict(deque)

    def check(self, key_id: str):
        """Record a request attempt and report whether it is allowed.

        Returns (allowed, limit, remaining, retry_after).
        """
        limit = limit_per_minute()
        now = time.time()
        hits = self._hits[key_id]

        # Drop timestamps outside the window.
        cutoff = now - WINDOW_SECONDS
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            oldest = hits[0]
            retry_after = max(1, math.ceil(oldest + WINDOW_SECONDS - now))
            return False, limit, 0, retry_after

        hits.append(now)
        remaining = limit - len(hits)
        return True, limit, remaining, 0


limiter = RateLimiter()
