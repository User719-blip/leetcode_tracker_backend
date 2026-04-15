import math
import threading
import time
from collections import deque

from fastapi import HTTPException, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


class _InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.time()
        with self._lock:
            bucket = self._events.setdefault(key, deque())
            threshold = now - window_seconds

            while bucket and bucket[0] <= threshold:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, math.ceil(window_seconds - (now - bucket[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.append(now)


class _RedisRateLimiter:
    def __init__(self, redis_url: str, key_prefix: str) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        full_key = f"{self._key_prefix}:{key}"

        count = self._client.incr(full_key)
        if count == 1:
            self._client.expire(full_key, window_seconds)

        if count > limit:
            ttl = self._client.ttl(full_key)
            retry_after = max(1, int(ttl) if ttl and ttl > 0 else 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )


class RateLimiter:
    def __init__(self) -> None:
        self._fallback = _InMemoryRateLimiter()
        self._backend: _RedisRateLimiter | _InMemoryRateLimiter = self._fallback

        settings = get_settings()
        if settings.redis_url.strip():
            try:
                redis_backend = _RedisRateLimiter(
                    redis_url=settings.redis_url,
                    key_prefix=settings.rate_limit_redis_prefix,
                )
                redis_backend._client.ping()
                self._backend = redis_backend
            except RedisError:
                self._backend = self._fallback

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        try:
            self._backend.hit(key=key, limit=limit, window_seconds=window_seconds)
        except RedisError:
            self._fallback.hit(key=key, limit=limit, window_seconds=window_seconds)

    @property
    def backend_name(self) -> str:
        return "redis" if isinstance(self._backend, _RedisRateLimiter) else "memory"

    @property
    def uses_redis(self) -> bool:
        return isinstance(self._backend, _RedisRateLimiter)


rate_limiter = RateLimiter()