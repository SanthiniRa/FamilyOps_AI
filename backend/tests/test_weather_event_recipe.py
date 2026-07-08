import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain_core.messages import HumanMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.weather_service import (  # noqa: E402
    WeatherService,
    _parse_coordinates,
    _weather_code_label,
)
from app.services.event_search_service import EventSearchService  # noqa: E402
from app.agents.orchestrator import FamilyOpsOrchestrator, _extract_location_from_message  # noqa: E402
from app.services.recipe_search_service import RecipeSearchService  # noqa: E402


def test_parse_coordinates_and_labels():
    assert _parse_coordinates("51.5074, -0.1278") == (51.5074, -0.1278)
    assert _weather_code_label(0) == "Clear sky"
    assert _weather_code_label(999) == "Code 999"


def test_weather_service_search_with_mocked_forecast():
    service = WeatherService()
    service._geocode = AsyncMock(return_value={
        "name": "London",
        "country": "United Kingdom",
        "admin1": "England",
        "latitude": 51.5072,
        "longitude": -0.1276,
    })
    service._forecast = AsyncMock(return_value={
        "current": {
            "time": "2026-06-10T12:00",
            "temperature_2m": 18.5,
            "apparent_temperature": 18.0,
            "precipitation": 0.0,
            "weather_code": 2,
            "wind_speed_10m": 10.2,
            "relative_humidity_2m": 60,
        },
        "hourly": {
            "time": ["2026-06-10T13:00"],
            "temperature_2m": [19.0],
            "precipitation_probability": [5],
            "weather_code": [2],
            "wind_speed_10m": [9.0],
        },
        "daily": {
            "time": ["2026-06-10"],
            "weather_code": [2],
            "temperature_2m_max": [20.0],
            "temperature_2m_min": [14.0],
            "precipitation_sum": [0.0],
            "wind_speed_10m_max": [12.0],
        },
    })

    result = asyncio.run(service.search("London", forecast_days=3))

    assert result["found"] is True
    assert result["location"]["name"] == "London"
    assert result["current"]["summary"] == "Partly cloudy"
    assert result["daily"][0]["temperature_max"] == 20.0


def test_weather_service_caches_repeated_searches():
    service = WeatherService()
    call_counts = {"geocode": 0, "forecast": 0}

    async def geocode_calls(location: str, *, country_code=None):
        call_counts["geocode"] += 1
        return {
            "name": "London",
            "country": "United Kingdom",
            "admin1": "England",
            "latitude": 51.5072,
            "longitude": -0.1276,
        }

    async def forecast_calls(latitude: float, longitude: float, days: int):
        call_counts["forecast"] += 1
        return {
            "current": {
                "time": "2026-06-10T12:00",
                "temperature_2m": 18.5,
                "apparent_temperature": 18.0,
                "precipitation": 0.0,
                "weather_code": 2,
                "wind_speed_10m": 10.2,
                "relative_humidity_2m": 60,
            },
            "hourly": {
                "time": ["2026-06-10T13:00"],
                "temperature_2m": [19.0],
                "precipitation_probability": [5],
                "weather_code": [2],
                "wind_speed_10m": [9.0],
            },
            "daily": {
                "time": ["2026-06-10"],
                "weather_code": [2],
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [14.0],
                "precipitation_sum": [0.0],
                "wind_speed_max": [12.0],
            },
        }

    service._geocode_uncached = geocode_calls  # type: ignore[method-assign]
    service._forecast_uncached = forecast_calls  # type: ignore[method-assign]

    first = asyncio.run(service.search("London", forecast_days=3))
    second = asyncio.run(service.search("London", forecast_days=3))

    assert first["location"]["name"] == "London"
    assert second["location"]["name"] == "London"
    assert call_counts["geocode"] == 1
    assert call_counts["forecast"] == 1


def test_event_service_normalizes_event():
    service = EventSearchService()
    event = service._normalize_event(
        {
            "id": "abc",
            "name": "Family Fun Day",
            "url": "https://example.com/event",
            "priceRanges": [
                {"min": 10, "max": 20, "currency": "GBP"},
            ],
            "dates": {
                "start": {"localDate": "2026-06-15", "localTime": "10:00:00"},
                "status": {"code": "onsale"},
            },
            "_embedded": {
                "venues": [
                    {
                        "name": "Town Hall",
                        "city": {"name": "London"},
                        "country": {"name": "United Kingdom"},
                        "address": {"line1": "1 High St"},
                        "postalCode": "SW1A 1AA",
                    }
                ]
            },
            "images": [{"url": "https://example.com/image.jpg"}],
        }
    )

    assert event["id"] == "abc"
    assert event["venue"]["city"] == "London"
    assert event["image"] == "https://example.com/image.jpg"
    assert event["cost_summary"] == "£10 to £20"


def test_event_search_service_with_mocked_http(monkeypatch):
    service = EventSearchService()
    service.ticketmaster_api_key = "test-key"

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "_embedded": {
                    "events": [
                        {
                            "id": "1",
                            "name": "Kids Theatre",
                            "url": "https://example.com/kids-theatre",
                            "dates": {"start": {"localDate": "2026-06-20", "localTime": "12:00:00"}},
                            "_embedded": {"venues": [{"name": "Hall", "city": {"name": "London"}, "country": {"name": "United Kingdom"}}]},
                            "images": [],
                        }
                    ]
                }
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    monkeypatch.setattr("app.services.event_search_service.httpx.AsyncClient", FakeClient)

    result = asyncio.run(service.search(query="family events", location="London", max_results=5))

    assert captured["params"]["countryCode"] == "GB"
    assert captured["params"]["includeFamily"] == "yes"
    assert result["results"][0]["name"] == "Kids Theatre"


def test_event_search_service_without_api_key_returns_empty_results():
    service = EventSearchService()
    service.ticketmaster_api_key = ""

    result = asyncio.run(service.search(query="family events", location="London", max_results=5))

    assert result["provider"] == "ticketmaster"
    assert result["results"] == []


def test_extract_location_strips_weekend_words():
    assert _extract_location_from_message("What's the weather in London this weekend") == "London"
    assert _extract_location_from_message("Find family-friendly events near Buckinghamshire this weekend") == "Buckinghamshire"


def test_orchestrator_routes_family_events_and_weather_without_llm():
    orchestrator = FamilyOpsOrchestrator()
    orchestrator.llm = None

    weather_intent = asyncio.run(orchestrator._detect_intent("What's the weather in London this weekend"))
    event_intent = asyncio.run(orchestrator._detect_intent("Find family-friendly events near Buckinghamshire"))
    web_intent = asyncio.run(orchestrator._detect_intent("Look up the latest advice online"))

    assert weather_intent == "weather"
    assert event_intent == "event"
    assert web_intent == "web"


def test_orchestrator_routes_school_holiday_activities_to_event():
    orchestrator = FamilyOpsOrchestrator()
    orchestrator.llm = None

    intent = asyncio.run(orchestrator._detect_intent("Look up the latest advice on UK school holiday activities"))

    assert intent == "event"


def test_web_search_agent_returns_structured_reply(monkeypatch):
    orchestrator = FamilyOpsOrchestrator()
    orchestrator.llm = None

    async def fake_web_search(query: str, max_results: int, fetch_pages: bool):
        return {
            "query": query,
            "provider": "duckduckgo",
            "pages": [
                {
                    "title": "UK School Holiday Activities",
                    "url": "https://example.com/activities",
                    "domain": "example.com",
                    "page_description": "Family days out, museums, parks, and craft ideas.",
                }
            ],
        }

    monkeypatch.setattr("app.agents.orchestrator.web_search_service.search", fake_web_search)

    state = {
        "messages": [HumanMessage(content="Look up the latest advice on UK school holiday activities")],
        "agent_name": "orchestrator",
        "workflow_id": "test-workflow",
        "context": {},
        "tools_called": [],
        "reply": "",
        "status": "",
        "error": None,
    }

    result = asyncio.run(orchestrator._web_search_agent_node(state))

    assert result["status"] == "completed"
    assert "UK School Holiday Activities" in result["reply"]
    assert "example.com/activities" in result["reply"]


def test_recipe_search_service_with_mocked_http(monkeypatch):
    service = RecipeSearchService()

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            if "search.php" in url:
                return FakeResponse(
                    {
                        "meals": [
                            {
                                "idMeal": "1001",
                                "strMeal": "Pasta Bake",
                                "strCategory": "Pasta",
                                "strArea": "British",
                                "strInstructions": "Cook pasta and bake.",
                                "strMealThumb": "https://example.com/pasta.jpg",
                                "strSource": "https://example.com/pasta",
                                "strYoutube": "",
                                "strTags": "Dinner,Quick",
                                "strIngredient1": "Pasta",
                                "strMeasure1": "200g",
                            }
                        ]
                    }
                )
            return FakeResponse({"meals": []})

    monkeypatch.setattr("app.services.recipe_search_service.httpx.AsyncClient", FakeClient)

    result = asyncio.run(service.search("pasta bake", max_results=5))

    assert result["provider"] == "themealdb"
    assert result["results"][0]["name"] == "Pasta Bake"
    assert "Pasta" in result["results"][0]["ingredients"]


def test_recipe_search_service_uses_ingredients_when_provided(monkeypatch):
    service = RecipeSearchService()
    captured = {"calls": []}

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            captured["calls"].append((url, params))
            if "filter.php" in url and params.get("i") == "rice":
                return FakeResponse(
                    {
                        "meals": [
                            {"idMeal": "1002", "strMeal": "Rice Bowl", "strCategory": "Rice", "strArea": "British"}
                        ]
                    }
                )
            if "lookup.php" in url:
                return FakeResponse(
                    {
                        "meals": [
                            {
                                "idMeal": "1002",
                                "strMeal": "Rice Bowl",
                                "strCategory": "Rice",
                                "strArea": "British",
                                "strInstructions": "Cook rice and serve.",
                                "strMealThumb": "https://example.com/rice.jpg",
                                "strSource": "https://example.com/rice",
                                "strYoutube": "",
                                "strTags": "Dinner",
                                "strIngredient1": "Rice",
                                "strMeasure1": "1 cup",
                            }
                        ]
                    }
                )
            return FakeResponse({"meals": []})

    monkeypatch.setattr("app.services.recipe_search_service.httpx.AsyncClient", FakeClient)

    result = asyncio.run(service.search("use what I have", max_results=5, ingredients=["rice", "rice"]))

    assert result["ingredients"] == ["rice"]
    assert result["results"][0]["name"] == "Rice Bowl"
    assert any("filter.php" in call[0] for call in captured["calls"])


def test_recipe_agent_uses_inventory_ingredients(monkeypatch):
    orchestrator = FamilyOpsOrchestrator()
    orchestrator.llm = None
    orchestrator.llm_provider = None
    orchestrator.llm_model = None
    captured = {}

    async def fake_search(query: str, max_results: int = 8, ingredient=None, ingredients=None, category=None):
        captured["query"] = query
        captured["ingredients"] = ingredients
        return {
            "query": query,
            "ingredients": ingredients or [],
            "results": [
                {"name": "Rice Bowl", "category": "Rice", "area": "British", "ingredients": ["Rice"]}
            ],
        }

    monkeypatch.setattr(
        "app.agents.orchestrator.recipe_search_service.search",
        fake_search,
    )
    monkeypatch.setattr("app.agents.orchestrator.event_bus.publish", AsyncMock())

    state = {
        "messages": [SimpleNamespace(content="give me the recipe with the grocery item available in the grocery")],
        "agent_name": "orchestrator",
        "workflow_id": "test-workflow",
        "context": {
            "db_context": {
                "pantry_items": [{"name": "rice", "quantity": 2, "unit": "cups"}],
                "grocery_lists": [
                    {
                        "name": "Weekly shop",
                        "items": [
                            {"name": "pasta", "checked": True, "quantity": 1},
                            {"name": "tomato sauce", "checked": False, "quantity": 1},
                        ],
                    }
                ],
            }
        },
        "tools_called": [],
        "reply": "",
        "status": "started",
        "error": None,
    }

    result = asyncio.run(orchestrator._recipe_agent_node(state))

    assert captured["ingredients"] == ["rice", "pasta"]
    assert result["context"]["resource"]["ingredients"] == ["rice", "pasta"]
