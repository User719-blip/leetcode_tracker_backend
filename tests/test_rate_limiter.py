from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from redis.exceptions import RedisError

from app.core import rate_limiter as rate_limiter_module


def test_in_memory_rate_limit_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: SimpleNamespace(redis_url="", rate_limit_redis_prefix="test:rl"),
    )

    limiter = rate_limiter_module.RateLimiter()
    assert limiter.backend_name == "memory"

    limiter.hit("test:key", limit=1, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        limiter.hit("test:key", limit=1, window_seconds=60)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers


def test_redis_init_failure_falls_back_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenRedisLimiter:
        def __init__(self, redis_url: str, key_prefix: str) -> None:
            raise RedisError("redis unavailable")

    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://localhost:6379/0", rate_limit_redis_prefix="test:rl"),
    )
    monkeypatch.setattr(rate_limiter_module, "_RedisRateLimiter", BrokenRedisLimiter)

    limiter = rate_limiter_module.RateLimiter()
    assert limiter.backend_name == "memory"


def test_redis_hit_failure_uses_in_memory_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingRedisLimiter:
        def __init__(self, redis_url: str, key_prefix: str) -> None:
            self._client = SimpleNamespace(ping=lambda: None)

        def hit(self, key: str, limit: int, window_seconds: int) -> None:
            raise RedisError("redis temporary failure")

    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://localhost:6379/0", rate_limit_redis_prefix="test:rl"),
    )
    monkeypatch.setattr(rate_limiter_module, "_RedisRateLimiter", FailingRedisLimiter)

    limiter = rate_limiter_module.RateLimiter()
    assert limiter.backend_name == "redis"

    limiter.hit("fallback:key", limit=1, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        limiter.hit("fallback:key", limit=1, window_seconds=60)

    assert exc_info.value.status_code == 429