from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.core.config import settings
from app.core.resilience import RetrySettings, retry_async
from app.core.logging import logger


def _clean_text(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_result_url(url: str) -> str:
    if not url:
        return ""

    if url.startswith("//"):
        url = f"https:{url}"

    parsed = urlparse(url)
    if _is_duckduckgo_ad_url(parsed):
        return ""
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return unquote(target[0])

    return unquote(url)


def _is_duckduckgo_ad_url(parsed) -> bool:
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    return host.endswith("duckduckgo.com") and (
        path == "/y.js"
        or path.startswith("/y.js/")
        or "ad_domain=" in query
        or "ad_provider=" in query
        or "click_metadata=" in query
        or "rut=" in query
    )


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, Any]] = []
        self._capture_kind: Optional[str] = None
        self._capture_buffer: List[str] = []
        self._current_result: Optional[Dict[str, Any]] = None

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        attr_map = dict(attrs)
        class_value = attr_map.get("class", "") or ""
        class_tokens = set(class_value.split())

        if tag == "a" and "result__a" in class_tokens:
            href = _normalize_result_url(attr_map.get("href", ""))
            self._current_result = {
                "title": "",
                "url": href,
                "domain": urlparse(href).netloc,
                "snippet": "",
                "source": "duckduckgo",
            }
            self._capture_kind = "title"
            self._capture_buffer = []
            return

        if self._current_result and (
            "result__snippet" in class_tokens
            or any(token.startswith("result__snippet") for token in class_tokens)
        ):
            self._capture_kind = "snippet"
            self._capture_buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture_kind:
            self._capture_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_kind == "title" and tag == "a":
            title = _clean_text("".join(self._capture_buffer))
            if self._current_result is not None:
                self._current_result["title"] = title
                if title:
                    self.results.append(self._current_result)
            self._capture_kind = None
            self._capture_buffer = []
            return

        if self._capture_kind == "snippet" and tag in {"div", "span", "a", "p"}:
            snippet = _clean_text("".join(self._capture_buffer))
            if self._current_result is not None:
                self._current_result["snippet"] = snippet
            self._capture_kind = None
            self._capture_buffer = []


class _DuckDuckGoLiteResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, Any]] = []
        self._capture_kind: Optional[str] = None
        self._capture_buffer: List[str] = []
        self._current_result: Optional[Dict[str, Any]] = None

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        attr_map = dict(attrs)
        class_value = attr_map.get("class", "") or ""
        class_tokens = set(class_value.split())
        href = attr_map.get("href", "") or ""

        if tag == "a" and (
            "result-link" in class_tokens
            or "result__a" in class_tokens
            or ("nofollow" in (attr_map.get("rel", "") or "").split() and href)
        ):
            normalized = _normalize_result_url(href)
            if not normalized:
                return
            self._current_result = {
                "title": "",
                "url": normalized,
                "domain": urlparse(normalized).netloc,
                "snippet": "",
                "source": "duckduckgo",
            }
            self._capture_kind = "title"
            self._capture_buffer = []
            return

        if self._current_result and (
            "result-snippet" in class_tokens
            or "result__snippet" in class_tokens
            or any(token.startswith("result-snippet") for token in class_tokens)
            or any(token.startswith("result__snippet") for token in class_tokens)
        ):
            self._capture_kind = "snippet"
            self._capture_buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture_kind:
            self._capture_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture_kind == "title" and tag == "a":
            title = _clean_text("".join(self._capture_buffer))
            if self._current_result is not None:
                self._current_result["title"] = title
                if title:
                    self.results.append(self._current_result)
            self._capture_kind = None
            self._capture_buffer = []
            return

        if self._capture_kind == "snippet" and tag in {"div", "span", "a", "p"}:
            snippet = _clean_text("".join(self._capture_buffer))
            if self._current_result is not None:
                self._current_result["snippet"] = snippet
            self._capture_kind = None
            self._capture_buffer = []


def _page_excerpt(html: str, max_chars: int = 700) -> Dict[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    description_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html,
        re.I | re.S,
    )

    title = _clean_text(title_match.group(1)) if title_match else ""
    description = _clean_text(description_match.group(1)) if description_match else ""

    body_text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    body_text = re.sub(r"<style[^>]*>.*?</style>", " ", body_text, flags=re.I | re.S)
    body_text = _clean_text(body_text)
    excerpt = body_text[:max_chars]

    return {
        "title": title,
        "description": description,
        "excerpt": excerpt,
    }


class WebSearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        raise NotImplementedError


class DuckDuckGoSearchProvider(WebSearchProvider):
    name = "duckduckgo"

    def __init__(self) -> None:
        self.timeout_seconds = max(5, int(getattr(settings, "web_search_timeout_seconds", 12)))
        self.retry_settings = RetrySettings(
            attempts=max(1, int(getattr(settings, "external_api_retry_attempts", 3))),
            base_delay_seconds=float(getattr(settings, "external_api_retry_base_delay_seconds", 0.25)),
            max_delay_seconds=float(getattr(settings, "external_api_retry_max_delay_seconds", 2.0)),
        )
        self.user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

    async def search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        params = {"q": query, "kl": "us-en"}
        headers = {"User-Agent": self.user_agent}

        parser = _DuckDuckGoResultParser()
        response_text = await self._search_html(params=params, headers=headers)
        if response_text:
            parser.feed(response_text)

        if not parser.results:
            lite_text = await self._search_lite(params=params, headers=headers)
            if lite_text:
                lite_parser = _DuckDuckGoLiteResultParser()
                lite_parser.feed(lite_text)
                parser.results.extend(lite_parser.results)

        cleaned: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        for result in parser.results:
            url = result.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            cleaned.append(
                {
                    "title": result.get("title", ""),
                    "url": url,
                    "domain": result.get("domain", ""),
                    "snippet": result.get("snippet", ""),
                    "source": self.name,
                }
            )
            if len(cleaned) >= max_results:
                break

        return cleaned

    async def _search_html(self, *, params: Dict[str, Any], headers: Dict[str, str]) -> str:
        try:
            return await retry_async(
                lambda: self._request_text(
                    "https://html.duckduckgo.com/html/",
                    params=params,
                    headers=headers,
                ),
                retry_settings=self.retry_settings,
                operation_name="web_search",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                logger.warning("web_search.duckduckgo_html_forbidden")
                return ""
            raise

    async def _search_lite(self, *, params: Dict[str, Any], headers: Dict[str, str]) -> str:
        try:
            return await retry_async(
                lambda: self._request_text(
                    "https://lite.duckduckgo.com/lite/",
                    params=params,
                    headers=headers,
                ),
                retry_settings=self.retry_settings,
                operation_name="web_search",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                logger.warning("web_search.duckduckgo_lite_forbidden")
                return ""
            raise

    async def _request_text(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers=headers or {},
            follow_redirects=True,
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.text


class TavilySearchProvider(WebSearchProvider):
    name = "tavily"

    def __init__(self) -> None:
        self.timeout_seconds = max(5, int(getattr(settings, "web_search_timeout_seconds", 12)))
        self.api_key = (getattr(settings, "web_search_tavily_api_key", "") or "").strip()
        self.search_depth = (getattr(settings, "web_search_tavily_search_depth", "basic") or "basic").strip().lower()
        self.retry_settings = RetrySettings(
            attempts=max(1, int(getattr(settings, "external_api_retry_attempts", 3))),
            base_delay_seconds=float(getattr(settings, "external_api_retry_base_delay_seconds", 0.25)),
            max_delay_seconds=float(getattr(settings, "external_api_retry_max_delay_seconds", 2.0)),
        )

    async def search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise ValueError("WEB_SEARCH_TAVILY_API_KEY is required for tavily web search")

        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max(1, min(max_results, 10)),
            "search_depth": self.search_depth if self.search_depth in {"basic", "advanced"} else "basic",
            "include_answer": False,
            "include_raw_content": False,
        }

        data = await retry_async(
            lambda: self._request_json("https://api.tavily.com/search", json=payload),
            retry_settings=self.retry_settings,
            operation_name="web_search",
        )

        results = data.get("results") or []
        cleaned: List[Dict[str, Any]] = []
        for result in results:
            url = _normalize_result_url(result.get("url", ""))
            if not url:
                continue
            cleaned.append(
                {
                    "title": result.get("title", ""),
                    "url": url,
                    "domain": urlparse(url).netloc,
                    "snippet": result.get("content", "") or result.get("raw_content", "") or "",
                    "score": result.get("score"),
                    "source": self.name,
                }
            )
            if len(cleaned) >= max_results:
                break

        return cleaned

    async def _request_json(self, url: str, *, json: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, json=json)
            response.raise_for_status()
            return response.json()


SUPPORTED_WEB_SEARCH_PROVIDERS = {"auto", "duckduckgo", "tavily"}


@dataclass(frozen=True)
class ResolvedWebSearchProvider:
    provider: WebSearchProvider
    name: str


def resolve_web_search_provider(requested_provider: Optional[str] = None) -> ResolvedWebSearchProvider:
    provider_name = (requested_provider or getattr(settings, "web_search_provider", "duckduckgo") or "duckduckgo").strip().lower()

    if provider_name not in SUPPORTED_WEB_SEARCH_PROVIDERS:
        logger.warning("web_search.unsupported_provider", provider=provider_name, fallback="duckduckgo")
        provider_name = "duckduckgo"

    if provider_name == "auto":
        tavily_api_key = (getattr(settings, "web_search_tavily_api_key", "") or "").strip()
        if tavily_api_key:
            return ResolvedWebSearchProvider(provider=TavilySearchProvider(), name="tavily")
        return ResolvedWebSearchProvider(provider=DuckDuckGoSearchProvider(), name="duckduckgo")

    if provider_name == "tavily":
        return ResolvedWebSearchProvider(provider=TavilySearchProvider(), name="tavily")

    return ResolvedWebSearchProvider(provider=DuckDuckGoSearchProvider(), name="duckduckgo")
