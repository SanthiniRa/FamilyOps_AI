import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.auth import AuthContext  # noqa: E402
from app.core.resilience import (  # noqa: E402
    AsyncTTLCache,
    RateLimitRule,
    RateLimitExceeded,
    enforce_search_rate_limit,
    shared_resilience_health,
    rate_limiter,
    retry_async,
)


class FakeRedisClient:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.counters = {}

    async def ping(self):
        return True

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def ttl(self, key):
        return self.ttls.get(key, -2)

    async def eval(self, script, numkeys, key, window_seconds):
        current = self.counters.get(key, 0) + 1
        self.counters[key] = current
        if key not in self.ttls:
            self.ttls[key] = int(window_seconds)
        return [current, self.ttls[key]]


class FakeCounter:
    def __init__(self):
        self.labels_calls = []
        self.inc_calls = []

    def labels(self, **labels):
        self.labels_calls.append(labels)
        return self

    def inc(self, amount=1):
        self.inc_calls.append(amount)


def test_retry_async_retries_transient_errors(monkeypatch):
    attempts = {"count": 0}
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    async def operation():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise httpx.TimeoutException("timeout")
        return "ok"

    monkeypatch.setattr("app.core.resilience.asyncio.sleep", fake_sleep)

    result = asyncio.run(retry_async(operation))

    assert result == "ok"
    assert attempts["count"] == 2
    assert len(sleep_calls) == 1


def test_async_ttl_cache_expires_entries(monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr("app.core.resilience.time.monotonic", lambda: clock["now"])
    from app.core import resilience

    monkeypatch.setattr(resilience, "_REDIS_CLIENT", None)
    monkeypatch.setattr(resilience, "_REDIS_UNAVAILABLE_UNTIL", float("inf"))

    cache = AsyncTTLCache()

    asyncio.run(cache.set("demo", {"value": 1}, ttl_seconds=10))
    assert asyncio.run(cache.get("demo")) == {"value": 1}

    clock["now"] = 111.0
    assert asyncio.run(cache.get("demo")) is None


def test_rate_limiter_blocks_after_limit(monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr("app.core.resilience.time.monotonic", lambda: clock["now"])
    from app.core import resilience

    monkeypatch.setattr(resilience, "_REDIS_CLIENT", None)
    monkeypatch.setattr(resilience, "_REDIS_UNAVAILABLE_UNTIL", float("inf"))

    limiter = rate_limiter
    limiter.clear()

    rule = RateLimitRule(max_requests=2, window_seconds=60)

    asyncio.run(limiter.consume("demo", rule))
    asyncio.run(limiter.consume("demo", rule))

    with pytest.raises(RateLimitExceeded) as exc_info:
        asyncio.run(limiter.consume("demo", rule))

    assert exc_info.value.retry_after_seconds > 0


def test_search_rate_limit_dependency_enforces_route_rules(monkeypatch):
    from app.core import resilience

    monkeypatch.setattr(resilience.settings, "web_search_rate_limit_requests_per_minute", 1)
    monkeypatch.setattr(resilience.settings, "external_rate_limit_window_seconds", 60)
    monkeypatch.setattr(resilience, "_REDIS_CLIENT", None)
    monkeypatch.setattr(resilience, "_REDIS_UNAVAILABLE_UNTIL", float("inf"))
    rate_limit_counter = FakeCounter()
    monkeypatch.setattr(resilience, "RATE_LIMIT_COUNTER", rate_limit_counter)
    resilience.rate_limiter.clear()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/web/search",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }
    request = Request(scope, receive=receive)
    auth_context = AuthContext(auth_type="api_token")

    asyncio.run(enforce_search_rate_limit(request, auth_context=auth_context))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(enforce_search_rate_limit(request, auth_context=auth_context))

    assert exc_info.value.status_code == 429
    assert rate_limit_counter.labels_calls[-1]["route"] == "/api/v1/web/search"
    assert rate_limit_counter.inc_calls == [1]


def test_redis_backed_cache_and_rate_limit(monkeypatch):
    from app.core import resilience

    fake_redis = FakeRedisClient()
    monkeypatch.setattr(resilience.settings, "enable_shared_resilience_redis", True)
    monkeypatch.setattr(resilience, "_REDIS_CLIENT", fake_redis)
    monkeypatch.setattr(resilience, "_REDIS_UNAVAILABLE_UNTIL", 0.0)

    cache = AsyncTTLCache(namespace="demo")
    asyncio.run(cache.set("alpha", {"value": 1}, ttl_seconds=30))
    cache.clear()

    assert asyncio.run(cache.get("alpha")) == {"value": 1}
    assert fake_redis.values["familyops:cache:demo:alpha"] == "{\"value\":1}"

    limiter = resilience.rate_limiter
    limiter.clear()
    rule = RateLimitRule(max_requests=1, window_seconds=60)

    asyncio.run(limiter.consume("demo-key", rule))

    with pytest.raises(RateLimitExceeded):
        asyncio.run(limiter.consume("demo-key", rule))


def test_cache_and_retry_metrics_increment(monkeypatch):
    from app.core import resilience

    monkeypatch.setattr(resilience, "_REDIS_CLIENT", None)
    monkeypatch.setattr(resilience, "_REDIS_UNAVAILABLE_UNTIL", float("inf"))
    cache_counter = FakeCounter()
    retry_counter = FakeCounter()
    monkeypatch.setattr(resilience, "CACHE_HIT_COUNTER", cache_counter)
    monkeypatch.setattr(resilience, "RETRY_COUNTER", retry_counter)

    cache = AsyncTTLCache(namespace="demo")
    asyncio.run(cache.set("alpha", {"value": 1}, ttl_seconds=30))
    assert asyncio.run(cache.get("alpha")) == {"value": 1}
    assert cache_counter.labels_calls[-1]["layer"] == "demo:local"

    async def fake_sleep(delay):
        return None

    async def operation():
        raise httpx.TimeoutException("timeout")

    with pytest.raises(httpx.TimeoutException):
        monkeypatch.setattr(resilience.asyncio, "sleep", fake_sleep)
        asyncio.run(
            retry_async(
                operation,
                retry_settings=resilience.RetrySettings(attempts=2),
                operation_name="demo-operation",
            )
        )

    assert retry_counter.labels_calls[-1]["operation"] == "demo-operation"
    assert retry_counter.inc_calls == [1]


def test_shared_resilience_health_reports_disabled_by_default():
    result = asyncio.run(shared_resilience_health())

    assert result["enabled"] is False
    assert result["available"] is False
    assert result["backend"] == "local"
