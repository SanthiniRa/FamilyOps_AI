from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.resilience import AsyncTTLCache, RetrySettings, retry_async


_WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


def _parse_coordinates(location: str) -> Optional[Tuple[float, float]]:
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", location or "")
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _weather_code_label(code: Optional[int]) -> str:
    if code is None:
        return "Unknown"
    return _WEATHER_CODE_MAP.get(int(code), f"Code {code}")


def _extract_daily_entries(weather: Dict[str, Any]) -> List[Dict[str, Any]]:
    daily = weather.get("daily") or {}
    times = daily.get("time") or []
    entries: List[Dict[str, Any]] = []
    for idx, day in enumerate(times):
        entries.append(
            {
                "date": day,
                "weather_code": (daily.get("weather_code") or [None])[idx] if idx < len(daily.get("weather_code") or []) else None,
                "summary": _weather_code_label((daily.get("weather_code") or [None])[idx] if idx < len(daily.get("weather_code") or []) else None),
                "temperature_max": (daily.get("temperature_2m_max") or [None])[idx] if idx < len(daily.get("temperature_2m_max") or []) else None,
                "temperature_min": (daily.get("temperature_2m_min") or [None])[idx] if idx < len(daily.get("temperature_2m_min") or []) else None,
                "precipitation_sum": (daily.get("precipitation_sum") or [None])[idx] if idx < len(daily.get("precipitation_sum") or []) else None,
                "wind_speed_max": (daily.get("wind_speed_10m_max") or [None])[idx] if idx < len(daily.get("wind_speed_10m_max") or []) else None,
            }
        )
    return entries


class WeatherService:
    def __init__(self) -> None:
        self.timeout_seconds = max(5, int(getattr(settings, "weather_timeout_seconds", 12)))
        self.default_country_code = (getattr(settings, "weather_default_country_code", "GB") or "GB").strip().upper()
        self.forecast_days = max(1, min(int(getattr(settings, "weather_forecast_days", 5)), 16))
        self.cache_ttl_seconds = max(1, int(getattr(settings, "weather_cache_ttl_seconds", 900)))
        self.retry_settings = RetrySettings(
            attempts=max(1, int(getattr(settings, "external_api_retry_attempts", 3))),
            base_delay_seconds=float(getattr(settings, "external_api_retry_base_delay_seconds", 0.25)),
            max_delay_seconds=float(getattr(settings, "external_api_retry_max_delay_seconds", 2.0)),
        )
        self._geocode_cache = AsyncTTLCache(namespace="weather-geocode")
        self._forecast_cache = AsyncTTLCache(namespace="weather-forecast")

    async def search(
        self,
        location: str,
        *,
        forecast_days: Optional[int] = None,
        country_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not location or not location.strip():
            raise ValueError("location is required")

        days = max(1, min(forecast_days or self.forecast_days, 16))
        resolved_location = location.strip()
        coordinates = _parse_coordinates(resolved_location)
        if coordinates is None:
            geo = await self._geocode(resolved_location, country_code=country_code or self.default_country_code)
            if not geo:
                return {
                    "query": resolved_location,
                    "provider": "open-meteo",
                    "found": False,
                    "message": f"No location found for '{resolved_location}'",
                    "results": [],
                }
            latitude = geo["latitude"]
            longitude = geo["longitude"]
            resolved_location = geo["name"]
            country = geo.get("country")
            admin1 = geo.get("admin1")
        else:
            latitude, longitude = coordinates
            country = None
            admin1 = None

        weather = await self._forecast(latitude, longitude, days)
        return {
            "query": location.strip(),
            "provider": "open-meteo",
            "found": True,
            "location": {
                "name": resolved_location,
                "country": country,
                "region": admin1,
                "latitude": latitude,
                "longitude": longitude,
            },
            "current": self._normalize_current(weather.get("current") or {}),
            "hourly": self._normalize_hourly(weather.get("hourly") or {}, limit=24),
            "daily": _extract_daily_entries(weather),
        }

    async def _geocode(self, location: str, *, country_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        cache_key = f"geocode::{location.strip().lower()}::{(country_code or '').strip().upper()}"
        return await self._geocode_cache.get_or_set(
            cache_key,
            self.cache_ttl_seconds,
            lambda: self._geocode_uncached(location, country_code=country_code),
        )

    async def _geocode_uncached(self, location: str, *, country_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        params = {
            "name": location,
            "count": 5,
            "language": "en",
            "format": "json",
        }
        if country_code:
            params["country_code"] = country_code

        data = await retry_async(
            lambda: self._request_json("https://geocoding-api.open-meteo.com/v1/search", params=params),
            retry_settings=self.retry_settings,
            operation_name="weather_geocode",
        )

        results = data.get("results") or []
        if not results and country_code:
            return await self._geocode(location, country_code=None)
        if not results:
            return None

        return results[0]

    async def _forecast(self, latitude: float, longitude: float, days: int) -> Dict[str, Any]:
        cache_key = f"forecast::{latitude:.4f}::{longitude:.4f}::{days}"
        return await self._forecast_cache.get_or_set(
            cache_key,
            self.cache_ttl_seconds,
            lambda: self._forecast_uncached(latitude, longitude, days),
        )

    async def _forecast_uncached(self, latitude: float, longitude: float, days: int) -> Dict[str, Any]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": [
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
                "relative_humidity_2m",
            ],
            "hourly": [
                "temperature_2m",
                "precipitation_probability",
                "weather_code",
                "wind_speed_10m",
            ],
            "daily": [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "wind_speed_10m_max",
            ],
            "forecast_days": days,
            "timezone": "auto",
        }

        return await retry_async(
            lambda: self._request_json("https://api.open-meteo.com/v1/forecast", params=params),
            retry_settings=self.retry_settings,
            operation_name="weather_forecast",
        )

    async def _request_json(
        self,
        url: str,
        *,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    def _normalize_current(self, current: Dict[str, Any]) -> Dict[str, Any]:
        code = current.get("weather_code")
        return {
            "time": current.get("time"),
            "temperature": current.get("temperature_2m"),
            "apparent_temperature": current.get("apparent_temperature"),
            "precipitation": current.get("precipitation"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "weather_code": code,
            "summary": _weather_code_label(code),
        }

    def _normalize_hourly(self, hourly: Dict[str, Any], *, limit: int = 24) -> List[Dict[str, Any]]:
        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        precipitation = hourly.get("precipitation_probability") or []
        codes = hourly.get("weather_code") or []
        wind = hourly.get("wind_speed_10m") or []

        entries: List[Dict[str, Any]] = []
        for idx, time_value in enumerate(times[:limit]):
            code = codes[idx] if idx < len(codes) else None
            entries.append(
                {
                    "time": time_value,
                    "temperature": temperatures[idx] if idx < len(temperatures) else None,
                    "precipitation_probability": precipitation[idx] if idx < len(precipitation) else None,
                    "wind_speed": wind[idx] if idx < len(wind) else None,
                    "weather_code": code,
                    "summary": _weather_code_label(code),
                }
            )
        return entries


weather_service = WeatherService()
