from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.resilience import AsyncTTLCache, RetrySettings, retry_async
from app.services.web_search_providers import (
    ResolvedWebSearchProvider,
    _DuckDuckGoResultParser,
    _normalize_result_url,
    _page_excerpt,
    resolve_web_search_provider,
)


class WebSearchService:
    def __init__(self) -> None:
        self.timeout_seconds = max(5, int(getattr(settings, "web_search_timeout_seconds", 12)))
        self.max_results = max(1, int(getattr(settings, "web_search_max_results", 5)))
        self.fetch_limit = max(0, int(getattr(settings, "web_search_fetch_limit", 3)))
        self.cache_ttl_seconds = max(1, int(getattr(settings, "web_search_cache_ttl_seconds", 300)))
        self.retry_settings = RetrySettings(
            attempts=max(1, int(getattr(settings, "external_api_retry_attempts", 3))),
            base_delay_seconds=float(getattr(settings, "external_api_retry_base_delay_seconds", 0.25)),
            max_delay_seconds=float(getattr(settings, "external_api_retry_max_delay_seconds", 2.0)),
        )
        self.cache = AsyncTTLCache(namespace="web-search")

        resolved_provider: ResolvedWebSearchProvider = resolve_web_search_provider()
        self.provider = resolved_provider.provider
        self.provider_name = resolved_provider.name
        logger.info("web_search.provider_selected", provider=self.provider_name)

    async def search(
        self,
        query: str,
        *,
        max_results: Optional[int] = None,
        fetch_pages: bool = True,
    ) -> Dict[str, Any]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("query is required")

        limit = max(1, min(max_results or self.max_results, 10))
        cache_key = f"{normalized_query.lower()}::{self.provider_name}::{limit}::{int(fetch_pages)}"
        return await self.cache.get_or_set(
            f"web-search::{cache_key}",
            self.cache_ttl_seconds,
            lambda: self._search_uncached(normalized_query, limit, fetch_pages=fetch_pages),
        )

    async def _search_uncached(self, query: str, limit: int, *, fetch_pages: bool) -> Dict[str, Any]:
        results = await self.provider.search(query, limit)

        pages: List[Dict[str, Any]] = []
        if fetch_pages and results and self.fetch_limit > 0:
            selected = results[: min(self.fetch_limit, len(results))]
            page_tasks = [self._fetch_page_summary(item["url"]) for item in selected if item.get("url")]
            if page_tasks:
                fetched = await asyncio.gather(*page_tasks, return_exceptions=True)
                for item, fetched_item in zip(selected, fetched):
                    if isinstance(fetched_item, Exception):
                        logger.warning(
                            "web_search.page_fetch_failed",
                            url=item.get("url"),
                            error=str(fetched_item),
                        )
                        continue
                    pages.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "domain": item.get("domain", ""),
                            "snippet": item.get("snippet", ""),
                            "page_title": fetched_item.get("title", ""),
                            "page_description": fetched_item.get("description", ""),
                            "page_excerpt": fetched_item.get("excerpt", ""),
                        }
                    )

        return {
            "query": query,
            "provider": self.provider_name,
            "results": results,
            "pages": pages,
        }

    async def _fetch_page_summary(self, url: str) -> Dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        response_text = await retry_async(
            lambda: self._request_text(url, headers=headers),
            retry_settings=self.retry_settings,
            operation_name="web_page_fetch",
        )

        return _page_excerpt(response_text)

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


web_search_service = WebSearchService()
