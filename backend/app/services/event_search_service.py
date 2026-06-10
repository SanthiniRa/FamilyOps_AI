from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.resilience import AsyncTTLCache, RetrySettings, retry_async


class EventSearchService:
    def __init__(self) -> None:
        self.timeout_seconds = max(5, int(getattr(settings, "event_search_timeout_seconds", 12)))
        self.provider = (getattr(settings, "event_search_provider", "ticketmaster") or "ticketmaster").strip().lower()
        self.default_country_code = (getattr(settings, "event_search_country_code", "GB") or "GB").strip().upper()
        self.ticketmaster_api_key = getattr(settings, "ticketmaster_api_key", "")
        self.cache_ttl_seconds = max(1, int(getattr(settings, "event_search_cache_ttl_seconds", 600)))
        self.retry_settings = RetrySettings(
            attempts=max(1, int(getattr(settings, "external_api_retry_attempts", 3))),
            base_delay_seconds=float(getattr(settings, "external_api_retry_base_delay_seconds", 0.25)),
            max_delay_seconds=float(getattr(settings, "external_api_retry_max_delay_seconds", 2.0)),
        )
        self.cache = AsyncTTLCache(namespace="event-search")

    async def search(
        self,
        *,
        query: Optional[str] = None,
        location: Optional[str] = None,
        postal_code: Optional[str] = None,
        radius_miles: Optional[int] = None,
        family_friendly: bool = True,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        if self.provider != "ticketmaster":
            raise ValueError(f"Unsupported event provider: {self.provider}")
        if not self.ticketmaster_api_key:
            raise ValueError("TICKETMASTER_API_KEY is required for event search")
        if not any([query, location, postal_code]):
            raise ValueError("query, location, or postal_code is required")

        cache_key = "::".join(
            [
                f"query={self._normalize_cache_part(query)}",
                f"location={self._normalize_cache_part(location)}",
                f"postal_code={self._normalize_cache_part(postal_code)}",
                f"radius={radius_miles or ''}",
                f"family={int(family_friendly)}",
                f"start={self._normalize_cache_part(start_date)}",
                f"end={self._normalize_cache_part(end_date)}",
                f"max={max_results}",
            ]
        )
        return await self.cache.get_or_set(
            f"events::{cache_key}",
            self.cache_ttl_seconds,
            lambda: self._search_uncached(
                query=query,
                location=location,
                postal_code=postal_code,
                radius_miles=radius_miles,
                family_friendly=family_friendly,
                start_date=start_date,
                end_date=end_date,
                max_results=max_results,
            ),
        )

    async def _search_uncached(
        self,
        *,
        query: Optional[str] = None,
        location: Optional[str] = None,
        postal_code: Optional[str] = None,
        radius_miles: Optional[int] = None,
        family_friendly: bool = True,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "apikey": self.ticketmaster_api_key,
            "countryCode": self.default_country_code,
            "size": max(1, min(max_results, 20)),
            "sort": "date,asc",
        }
        if query:
            params["keyword"] = query.strip()
        if location:
            params["city"] = location.strip()
        if postal_code:
            params["postalCode"] = postal_code.strip()
        if radius_miles:
            params["radius"] = max(1, min(radius_miles, 100))
            params["unit"] = "miles"
        if family_friendly:
            params["includeFamily"] = "yes"
        if start_date:
            params["startDateTime"] = self._normalize_iso_datetime(start_date, start_of_day=True)
        if end_date:
            params["endDateTime"] = self._normalize_iso_datetime(end_date, start_of_day=False)

        data = await retry_async(
            lambda: self._request_json("https://app.ticketmaster.com/discovery/v2/events.json", params=params),
            retry_settings=self.retry_settings,
            operation_name="event_search",
        )

        events = (data.get("_embedded") or {}).get("events") or []
        return {
            "provider": "ticketmaster",
            "query": query,
            "location": location,
            "postal_code": postal_code,
            "family_friendly": family_friendly,
            "results": [self._normalize_event(event) for event in events[:max_results]],
        }

    def _normalize_iso_datetime(self, value: str, *, start_of_day: bool) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=None)
        return parsed.isoformat(timespec="seconds") + "Z"

    def _normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        dates = event.get("dates") or {}
        start = (dates.get("start") or {})
        venues = ((event.get("_embedded") or {}).get("venues") or [])
        venue = venues[0] if venues else {}
        images = event.get("images") or []
        image_url = images[0].get("url") if images else None

        return {
            "id": event.get("id"),
            "name": event.get("name"),
            "url": event.get("url"),
            "image": image_url,
            "date": start.get("localDate"),
            "time": start.get("localTime"),
            "status": (dates.get("status") or {}).get("code"),
            "venue": {
                "name": venue.get("name"),
                "city": (venue.get("city") or {}).get("name"),
                "state": (venue.get("state") or {}).get("name"),
                "country": (venue.get("country") or {}).get("name"),
                "address": (venue.get("address") or {}).get("line1"),
                "postal_code": venue.get("postalCode"),
            },
        }

    async def _request_json(self, url: str, *, params: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    def _normalize_cache_part(self, value: Optional[str]) -> str:
        return (value or "").strip().lower()


event_search_service = EventSearchService()
