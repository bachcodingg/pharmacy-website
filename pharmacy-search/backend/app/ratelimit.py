"""In-process sliding-window rate limiting.

The auth routes accepted unlimited attempts from one IP. PBKDF2 at 390k
iterations is strong per guess but costs ~100ms of CPU per attempt, so the
login endpoint was simultaneously a credential-stuffing target and a cheap
way to saturate the single shared machine.

This is deliberately a few dozen lines rather than a dependency: the
deployment is one process on one machine, where an in-memory window is exact.
The moment a second machine exists this has to move to Redis or the edge -
the interface is small enough that swapping the backing store is local.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app import config


class SlidingWindowLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float) -> float:
        """Record a hit. Returns 0.0 if allowed, else seconds until retry."""
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return max(0.0, bucket[0] + window_seconds - now)
            bucket.append(now)
            return 0.0

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    def prune(self, older_than: float = 3600.0) -> None:
        """Drop buckets nothing has touched recently, so a flood of distinct
        keys cannot grow the dict without bound."""
        cutoff = time.monotonic() - older_than
        with self._lock:
            for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                del self._hits[key]


_limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    # Fly terminates TLS and forwards the original address; fall back to the
    # socket peer when running without a proxy. Only trust the header because
    # this app is always deployed behind one - a direct-to-internet deployment
    # would have to stop reading it.
    forwarded = request.headers.get("fly-client-ip") or request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str, limit: int, window_seconds: float, subject: str = "") -> None:
    """Raise 429 when `bucket` has been hit more than `limit` times in the window.

    `subject` narrows the key beyond the IP - passing the submitted email
    means one attacker cannot lock every account from one address, and one
    account cannot be brute-forced from many."""
    if not config.RATE_LIMIT_ENABLED:
        return
    key = f"{bucket}:{client_ip(request)}"
    if subject:
        key = f"{key}:{subject.lower()}"
    retry_after = _limiter.check(key, limit, window_seconds)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


def reset_all() -> None:
    _limiter.reset()


def prune() -> None:
    _limiter.prune()
