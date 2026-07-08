from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.core.logging import logger
from app.services.event_search_service import event_search_service
from app.services.web_search_service import web_search_service


_COST_PATTERN = re.compile(
    r"(?:£|\$|€)\s?\d+(?:\.\d{1,2})?(?:\s?(?:-|to)\s?(?:£|\$|€)\s?\d+(?:\.\d{1,2})?)?|free",
    re.IGNORECASE,
)
_TIME_PATTERN = re.compile(
    r"\b(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s?(?:am|pm)?\b",
    re.IGNORECASE,
)
_DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}\b"),
    re.compile(r"\b[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b"),
]
_DURATION_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:minutes?|mins?|hours?|hrs?)\b",
    re.IGNORECASE,
)
_TRANSPORT_KEYWORDS = [
    "bus",
    "train",
    "car",
    "drive",
    "walking",
    "walk",
    "tube",
    "tram",
    "cycle",
    "bike",
    "parking",
]


class ActivitySearchService:
    async def search(
        self,
        query: str,
        *,
        location: Optional[str] = None,
        source_domains: Optional[List[str]] = None,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("query is required")

        results: List[Dict[str, Any]] = []
        pages: List[Dict[str, Any]] = []
        errors: List[str] = []

        event_payload = await self._safe_event_search(
            normalized_query,
            location=location,
            max_results=max_results,
            errors=errors,
        )
        if event_payload:
            results.extend(self._normalize_event_results(event_payload))

        web_payload = await self._safe_web_search(
            normalized_query,
            location=location,
            source_domains=source_domains,
            max_results=max_results,
            errors=errors,
        )
        if web_payload:
            results.extend(self._normalize_web_results(web_payload))
            pages.extend(self._normalize_web_pages(web_payload))

        deduped = self._dedupe_results(results)
        deduped_pages = self._dedupe_web_items(pages)

        return {
            "query": normalized_query,
            "location": location,
            "results": deduped[:max_results],
            "pages": deduped_pages[:max_results],
            "sources": {
                "events": bool(event_payload),
                "web": bool(web_payload),
            },
            "errors": errors,
        }

    async def _safe_event_search(
        self,
        query: str,
        *,
        location: Optional[str],
        max_results: int,
        errors: List[str],
    ) -> Optional[Dict[str, Any]]:
        try:
            return await event_search_service.search(
                query=query,
                location=location,
                family_friendly=True,
                max_results=max_results,
            )
        except Exception as exc:
            logger.warning("activity_search.event_search_failed", error=str(exc))
            errors.append(f"events: {exc}")
            return None

    async def _safe_web_search(
        self,
        query: str,
        *,
        location: Optional[str],
        source_domains: Optional[List[str]],
        max_results: int,
        errors: List[str],
    ) -> Optional[Dict[str, Any]]:
        search_query = query if not location else f"{query} {location}"
        domains = self._normalize_domains(source_domains)

        if domains:
            try:
                return await self._search_source_domains(
                    search_query,
                    domains=domains,
                    max_results=max_results,
                )
            except Exception as exc:
                logger.warning("activity_search.site_scoped_web_search_failed", error=str(exc))
                errors.append(f"web: {exc}")
                return None

        try:
            return await web_search_service.search(
                search_query,
                max_results=max_results,
                fetch_pages=True,
            )
        except Exception as exc:
            logger.warning("activity_search.web_search_failed", error=str(exc))
            errors.append(f"web: {exc}")
            return None

    async def _search_source_domains(
        self,
        search_query: str,
        *,
        domains: List[str],
        max_results: int,
    ) -> Dict[str, Any]:
        combined_results: List[Dict[str, Any]] = []
        combined_pages: List[Dict[str, Any]] = []
        per_domain_limit = max(1, min(max_results, 2))

        for domain in domains:
            scoped_query = f"site:{domain} {search_query}".strip()
            payload = await web_search_service.search(
                scoped_query,
                max_results=per_domain_limit,
                fetch_pages=True,
            )
            combined_results.extend(payload.get("results") or [])
            combined_pages.extend(payload.get("pages") or [])

        return {
            "query": search_query,
            "provider": web_search_service.provider_name,
            "mode": "site_scoped",
            "source_domains": domains,
            "results": self._dedupe_web_items(combined_results),
            "pages": self._dedupe_web_items(combined_pages),
        }

    def _normalize_event_results(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in payload.get("results") or []:
            venue = item.get("venue") or {}
            normalized.append(
                {
                    "type": "activity",
                    "source": "event_search",
                    "title": item.get("name") or "Untitled activity",
                    "url": item.get("url") or "",
                    "date": item.get("date"),
                    "time": item.get("time"),
                    "cost": item.get("cost_summary") or self._format_price_ranges(item.get("price_ranges") or []),
                    "transport": None,
                    "time_taken": None,
                    "venue": venue,
                    "location": ", ".join(
                        part for part in [
                            venue.get("name"),
                            venue.get("city"),
                            venue.get("country"),
                        ]
                        if part
                    ),
                    "summary": "Ticketed event search result",
                }
            )
        return normalized

    def _normalize_web_results(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        source_results = payload.get("pages") or payload.get("results") or []

        for item in source_results:
            title = item.get("page_title") or item.get("title") or "Untitled activity"
            description = item.get("page_description") or item.get("snippet") or ""
            excerpt = item.get("page_excerpt") or ""
            blob = " ".join(part for part in [title, description, excerpt] if part).strip()

            normalized.append(
                {
                    "type": "activity",
                    "source": "web_search",
                    "title": title,
                    "url": item.get("url") or "",
                    "date": self._extract_date(blob),
                    "time": self._extract_time(blob),
                    "cost": self._extract_cost(blob),
                    "transport": self._extract_transport(blob),
                    "time_taken": self._extract_duration(blob),
                    "venue": {},
                    "location": item.get("domain") or "",
                    "summary": description or excerpt or title,
                }
            )
        return normalized

    def _normalize_web_pages(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        pages: List[Dict[str, Any]] = []
        for item in payload.get("pages") or []:
            pages.append(
                {
                    "title": item.get("page_title") or item.get("title") or "Untitled page",
                    "url": item.get("url") or "",
                    "domain": item.get("domain") or "",
                    "snippet": item.get("page_description") or item.get("page_excerpt") or item.get("snippet") or "",
                    "page_title": item.get("page_title") or item.get("title") or "Untitled page",
                    "page_description": item.get("page_description") or "",
                    "page_excerpt": item.get("page_excerpt") or "",
                }
            )
        return pages

    def _dedupe_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in results:
            key = (str(item.get("title") or "").lower(), str(item.get("url") or "").lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _dedupe_web_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            url = str(item.get("url") or "").strip().lower()
            if not url:
                domain = str(item.get("domain") or "").strip().lower()
                title = str(item.get("title") or item.get("page_title") or "").strip().lower()
                url = "::".join(part for part in [domain, title] if part)
            if not url or url in seen:
                continue
            seen.add(url)
            deduped.append(item)
        return deduped

    def _normalize_domains(self, domains: Optional[List[str]]) -> List[str]:
        normalized: List[str] = []
        seen: set[str] = set()
        for domain in domains or []:
            cleaned = self._normalize_domain(domain)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    def _normalize_domain(self, value: str) -> str:
        candidate = (value or "").strip().lower()
        if not candidate:
            return ""

        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host

    def _extract_cost(self, text: str) -> Optional[str]:
        match = _COST_PATTERN.search(text or "")
        if not match:
            return None
        value = " ".join(match.group(0).split())
        return value[:80]

    def _extract_date(self, text: str) -> Optional[str]:
        for pattern in _DATE_PATTERNS:
            match = pattern.search(text or "")
            if match:
                return " ".join(match.group(0).split())
        return None

    def _extract_time(self, text: str) -> Optional[str]:
        match = _TIME_PATTERN.search(text or "")
        if not match:
            return None
        return " ".join(match.group(0).split())

    def _extract_transport(self, text: str) -> Optional[str]:
        lowered = (text or "").lower()
        for keyword in _TRANSPORT_KEYWORDS:
            if keyword in lowered:
                if keyword == "drive":
                    return "By car"
                if keyword == "walk":
                    return "On foot"
                if keyword == "bike":
                    return "By bike"
                return f"By {keyword}"
        return None

    def _extract_duration(self, text: str) -> Optional[str]:
        match = _DURATION_PATTERN.search(text or "")
        if not match:
            return None
        return " ".join(match.group(0).split())

    def _format_price_ranges(self, price_ranges: List[Dict[str, Any]]) -> Optional[str]:
        if not price_ranges:
            return None

        ranges: List[str] = []
        for price_range in price_ranges:
            minimum = price_range.get("min")
            maximum = price_range.get("max")
            currency = str(price_range.get("currency") or "").strip().upper()

            if minimum in (None, "") and maximum in (None, ""):
                continue

            if minimum == 0 and maximum == 0:
                ranges.append("Free")
                continue

            min_text = self._format_currency_value(minimum, currency)
            max_text = self._format_currency_value(maximum, currency)

            if min_text and max_text and min_text != max_text:
                ranges.append(f"{min_text} to {max_text}")
            else:
                ranges.append(min_text or max_text)

        if not ranges:
            return None

        return " / ".join(dict.fromkeys(ranges))

    def _format_currency_value(self, value: Any, currency: str) -> str:
        if value in (None, ""):
            return ""

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return str(value)

        if numeric.is_integer():
            amount = f"{int(numeric)}"
        else:
            amount = f"{numeric:.2f}".rstrip("0").rstrip(".")

        symbols = {
            "GBP": "£",
            "USD": "$",
            "EUR": "€",
        }
        prefix = symbols.get(currency, f"{currency} " if currency else "")
        return f"{prefix}{amount}"


activity_search_service = ActivitySearchService()
