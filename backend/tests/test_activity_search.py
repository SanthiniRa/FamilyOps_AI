import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.orchestrator import _activity_source_domains  # noqa: E402
from app.services.activity_search_service import activity_search_service  # noqa: E402


def test_activity_search_merges_event_and_web_results(monkeypatch):
    async def fake_event_search(query: str, *, location=None, family_friendly=True, max_results=5):
        return {
            "query": query,
            "location": location,
            "results": [
                {
                    "name": "Family Fun Day",
                    "url": "https://example.com/fun-day",
                    "date": "2026-07-20",
                    "time": "10:00:00",
                    "cost_summary": "£10 to £20",
                    "price_ranges": [{"min": 10, "max": 20, "currency": "GBP"}],
                    "venue": {"name": "Town Hall", "city": "London", "country": "United Kingdom"},
                }
            ],
        }

    async def fake_web_search(query: str, max_results: int, fetch_pages: bool):
        return {
            "query": query,
            "provider": "duckduckgo",
            "pages": [
                {
                    "title": "Museum Workshop",
                    "url": "https://example.com/workshop",
                    "domain": "example.com",
                    "page_description": "Free bus shuttle, 30 mins from the station, 2pm start.",
                    "page_excerpt": "Free bus shuttle, 30 mins from the station, 2pm start.",
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.activity_search_service.event_search_service.search",
        fake_event_search,
    )
    monkeypatch.setattr(
        "app.services.activity_search_service.web_search_service.search",
        fake_web_search,
    )

    result = asyncio.run(activity_search_service.search("kids activities in London", location="London", max_results=5))

    assert result["query"] == "kids activities in London"
    assert result["sources"]["events"] is True
    assert result["sources"]["web"] is True
    assert len(result["results"]) == 2
    assert result["results"][0]["source"] == "event_search"
    assert result["results"][0]["cost"] == "£10 to £20"
    assert result["results"][1]["source"] == "web_search"
    assert result["results"][1]["cost"] == "Free"
    assert result["results"][1]["transport"] == "By bus"
    assert result["results"][1]["time_taken"] == "30 mins"


def test_activity_search_scopes_web_queries_to_domains(monkeypatch):
    calls = []

    async def fake_event_search(query: str, *, location=None, family_friendly=True, max_results=5):
        return {"query": query, "location": location, "results": []}

    async def fake_web_search(query: str, max_results: int, fetch_pages: bool):
        calls.append(query)
        return {
            "query": query,
            "provider": "duckduckgo",
            "pages": [
                {
                    "title": "National Trust Family Event",
                    "url": "https://nationaltrust.org.uk/example",
                    "domain": "nationaltrust.org.uk",
                    "page_description": "Free bus from the station, 2pm start, 45 mins.",
                    "page_excerpt": "Free bus from the station, 2pm start, 45 mins.",
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.activity_search_service.event_search_service.search",
        fake_event_search,
    )
    monkeypatch.setattr(
        "app.services.activity_search_service.web_search_service.search",
        fake_web_search,
    )

    result = asyncio.run(
        activity_search_service.search(
            "kids activities in London",
            location="London",
            source_domains=["nationaltrust.org.uk", "nhm.ac.uk"],
            max_results=5,
        )
    )

    assert calls[0].startswith("site:nationaltrust.org.uk")
    assert calls[1].startswith("site:nhm.ac.uk")
    assert result["results"][0]["source"] == "web_search"
    assert result["results"][0]["cost"] == "Free"
    assert result["results"][0]["transport"] == "By bus"
    assert result["results"][0]["time_taken"] == "45 mins"


def test_activity_source_domains_include_family_sites():
    domains = _activity_source_domains("Find family activities in London")

    assert domains is not None
    assert "ngs.org.uk" in domains
    assert "nationaltrust.org.uk" in domains
    assert "artscouncil.org.uk" in domains
    assert "nhm.ac.uk" in domains
    assert "britishmuseum.org" in domains
    assert "dayoutwiththekids.co.uk" in domains
    assert "timeout.com" in domains
    assert "familiesonline.co.uk" in domains
    assert "primarytimes.co.uk" in domains
    assert "familyinfo.buckinghamshire.gov.uk" in domains
