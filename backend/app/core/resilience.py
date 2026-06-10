from __future__ import annotations

import asyncio
import json
import math
import random
import threading
import time
from collections import defaultdict, deque
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Deque, Dict, Optional, TypeVar

import httpx
from fastapi import Depends, HTTPException, Request, status
from redis.exceptions import RedisError

try:
    import redis.asyncio as redis_async
except Exception:  # pragma: no cover - redis is an optional runtime dependency in tests
    redis_async = None

from app.core.auth import AuthContext, get_auth_context
from app.core.config import settings
from app.core.logging import logger
from app.observability.metrics import CACHE_HIT_COUNTER, RATE_LIMIT_COUNTER, RETRY_COUNTER


T = TypeVar("T")

REDIS_CACHE_PREFIX = "familyops:cache"
REDIS_RATE_LIMIT_PREFIX = "familyops:rate-limit"
_REDIS_CLIENT: Any = None
_REDIS_UNAVAILABLE_UNTIL = 0.0
_REDIS_BACKOFF_SECONDS = 30.0
_REDIS_OPERATION_TIMEOUT_SECONDS = 0.25


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    expires_at: float


class AsyncTTLCache:
    def __init__(self, namespace: str = "cache") -> None:
        self._entries: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._namespace = namespace

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _redis_key(self, key: str) -> str:
        return f"{REDIS_CACHE_PREFIX}:{self._namespace}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                local_value = None
            elif entry.expires_at <= now:
                self._entries.pop(key, None)
                local_value = None
            else:
                CACHE_HIT_COUNTER.labels(layer=f"{self._namespace}:local").inc()
                return entry.value

        redis_hit = await _redis_cache_get(self._redis_key(key))
        if redis_hit is None:
            return local_value

        redis_value, ttl_seconds = redis_hit
        CACHE_HIT_COUNTER.labels(layer=f"{self._namespace}:redis").inc()
        if ttl_seconds > 0:
            await self.set(key, redis_value, ttl_seconds)
        if redis_value is None:
            return local_value
        return redis_value

    async def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        ttl = max(0.0, float(ttl_seconds))
        expires_at = time.monotonic() + ttl
        with self._lock:
            self._entries[key] = CacheEntry(value=value, expires_at=expires_at)

        await _redis_cache_set(self._redis_key(key), value, ttl)

    async def get_or_set(
        self,
        key: str,
        ttl_seconds: float,
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await factory()
        await self.set(key, value, ttl_seconds)
        return value


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(payload: str) -> Any:
    return json.loads(payload)


async def _get_redis_client() -> Optional[Any]:
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE_UNTIL

    if redis_async is None:
        return None

    if not bool(getattr(settings, "enable_shared_resilience_redis", False)):
        return None

    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    now = time.monotonic()
    if now < _REDIS_UNAVAILABLE_UNTIL:
        return None

    redis_url = (getattr(settings, "redis_url", "") or "").strip()
    if not redis_url:
        return None

    try:
        client = redis_async.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        await asyncio.wait_for(client.ping(), timeout=_REDIS_OPERATION_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        with suppress(Exception):
            if "client" in locals():
                await asyncio.wait_for(client.aclose(), timeout=_REDIS_OPERATION_TIMEOUT_SECONDS)
        _REDIS_UNAVAILABLE_UNTIL = now + _REDIS_BACKOFF_SECONDS
        logger.debug("resilience.redis_unavailable", error=str(exc))
        return None

    _REDIS_CLIENT = client
    _REDIS_UNAVAILABLE_UNTIL = 0.0
    return client


def _disable_redis_client() -> None:
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE_UNTIL
    _REDIS_CLIENT = None
    _REDIS_UNAVAILABLE_UNTIL = time.monotonic() + _REDIS_BACKOFF_SECONDS


async def _redis_cache_get(key: str) -> Optional[tuple[Any, float]]:
    client = await _get_redis_client()
    if client is None:
        return None

    try:
        payload = await asyncio.wait_for(client.get(key), timeout=_REDIS_OPERATION_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, RedisError, OSError, httpx.TransportError):  # pragma: no cover - network dependent
        _disable_redis_client()
        return None

    if payload is None:
        return None

    try:
        ttl_seconds = float(await asyncio.wait_for(client.ttl(key), timeout=_REDIS_OPERATION_TIMEOUT_SECONDS))
    except (asyncio.TimeoutError, RedisError, OSError, httpx.TransportError):  # pragma: no cover - network dependent
        _disable_redis_client()
        ttl_seconds = 0.0

    with suppress(Exception):
        return _json_loads(payload), max(0.0, ttl_seconds)
    return None


async def _redis_cache_set(key: str, value: Any, ttl_seconds: float) -> None:
    client = await _get_redis_client()
    if client is None:
        return

    try:
        await asyncio.wait_for(
            client.set(key, _json_dumps(value), ex=max(1, int(ttl_seconds))),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, TypeError, ValueError):
        return
    except (RedisError, OSError, httpx.TransportError):  # pragma: no cover - network dependent
        _disable_redis_client()
        return


def _redis_rate_limit_key(key: str) -> str:
    return f"{REDIS_RATE_LIMIT_PREFIX}:{key}"


async def _redis_rate_limit_consume(key: str, rule: RateLimitRule) -> Optional[float]:
    client = await _get_redis_client()
    if client is None:
        return None

    redis_key = _redis_rate_limit_key(key)
    script = """
    local current = redis.call("INCR", KEYS[1])
    if current == 1 then
        redis.call("EXPIRE", KEYS[1], ARGV[1])
    end
    local ttl = redis.call("TTL", KEYS[1])
    return {current, ttl}
    """

    try:
        current, ttl = await asyncio.wait_for(
            client.eval(script, 1, redis_key, int(rule.window_seconds)),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, RedisError, OSError, httpx.TransportError):  # pragma: no cover - network dependent
        _disable_redis_client()
        return None

    if int(current) <= int(rule.max_requests):
        return None

    if int(ttl) > 0:
        return float(ttl)

    return float(rule.window_seconds)


async def shared_resilience_health() -> Dict[str, Any]:
    enabled = bool(getattr(settings, "enable_shared_resilience_redis", False))
    if not enabled:
        return {
            "enabled": False,
            "backend": "local",
            "available": False,
            "detail": "shared redis disabled",
        }

    client = await _get_redis_client()
    if client is None:
        return {
            "enabled": True,
            "backend": "redis",
            "available": False,
            "detail": "redis unavailable",
        }

    return {
        "enabled": True,
        "backend": "redis",
        "available": True,
        "detail": "redis connected",
    }


@dataclass(frozen=True)
class RetrySettings:
    attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0


def _should_retry_httpx_error(error: Exception) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return True

    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        return status_code in {408, 425, 429} or status_code >= 500

    return False


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    retry_settings: Optional[RetrySettings] = None,
    retryable: Callable[[Exception], bool] = _should_retry_httpx_error,
    operation_name: str = "external_http",
) -> T:
    config = retry_settings or RetrySettings()
    attempts = max(1, int(config.attempts))
    base_delay = max(0.0, float(config.base_delay_seconds))
    max_delay = max(base_delay, float(config.max_delay_seconds))

    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as error:  # noqa: BLE001
            last_error = error
            if attempt >= attempts or not retryable(error):
                raise

            RETRY_COUNTER.labels(operation=operation_name).inc()
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            jitter = delay * random.uniform(0.8, 1.2)
            await asyncio.sleep(max(0.0, jitter))

    if last_error is not None:
        raise last_error

    raise RuntimeError("retry_async exhausted without returning or raising")


@dataclass(frozen=True)
class RateLimitRule:
    max_requests: int
    window_seconds: int


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = max(0.0, float(retry_after_seconds))


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()

    async def consume(self, key: str, rule: RateLimitRule) -> None:
        if rule.max_requests <= 0 or rule.window_seconds <= 0:
            return

        retry_after = await _redis_rate_limit_consume(key, rule)
        if retry_after is not None:
            raise RateLimitExceeded(retry_after)

        now = time.monotonic()
        window_start = now - float(rule.window_seconds)

        with self._lock:
            bucket = self._requests[key]
            while bucket and bucket[0] <= window_start:
                bucket.popleft()

            if len(bucket) >= rule.max_requests:
                retry_after = max(0.0, bucket[0] + float(rule.window_seconds) - now)
                raise RateLimitExceeded(retry_after)

            bucket.append(now)


rate_limiter = SlidingWindowRateLimiter()


def _route_rate_limit_rule(path: str) -> Optional[RateLimitRule]:
    rules = {
        "/api/v1/web/search": RateLimitRule(
            max_requests=max(1, int(getattr(settings, "web_search_rate_limit_requests_per_minute", 20))),
            window_seconds=max(1, int(getattr(settings, "external_rate_limit_window_seconds", 60))),
        ),
        "/api/v1/weather/search": RateLimitRule(
            max_requests=max(1, int(getattr(settings, "weather_rate_limit_requests_per_minute", 30))),
            window_seconds=max(1, int(getattr(settings, "external_rate_limit_window_seconds", 60))),
        ),
        "/api/v1/events/search": RateLimitRule(
            max_requests=max(1, int(getattr(settings, "event_search_rate_limit_requests_per_minute", 20))),
            window_seconds=max(1, int(getattr(settings, "external_rate_limit_window_seconds", 60))),
        ),
        "/api/v1/recipes/search": RateLimitRule(
            max_requests=max(1, int(getattr(settings, "recipe_search_rate_limit_requests_per_minute", 30))),
            window_seconds=max(1, int(getattr(settings, "external_rate_limit_window_seconds", 60))),
        ),
    }
    return rules.get(path)


async def enforce_search_rate_limit(
    request: Request,
    auth_context: AuthContext = Depends(get_auth_context),
) -> None:
    rule = _route_rate_limit_rule(request.url.path)
    if rule is None:
        return

    subject = auth_context.user.id if auth_context.user else auth_context.auth_type
    client_ip = request.client.host if request.client else "unknown"
    key = f"{request.method}:{request.url.path}:{subject}:{client_ip}"

    try:
        await rate_limiter.consume(key, rule)
    except RateLimitExceeded as exc:
        RATE_LIMIT_COUNTER.labels(route=request.url.path).inc()
        retry_after = max(1, int(math.ceil(exc.retry_after_seconds)))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again shortly.",
            headers={"Retry-After": str(retry_after)},
        ) from exc
