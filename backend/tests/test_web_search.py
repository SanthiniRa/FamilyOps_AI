import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.web_search_service import (  # noqa: E402
    WebSearchService,
    _DuckDuckGoResultParser,
    _normalize_result_url,
    _page_excerpt,
)
from app.services.web_search_providers import (  # noqa: E402
    DuckDuckGoSearchProvider,
    TavilySearchProvider,
    resolve_web_search_provider,
)


def test_normalize_result_url_decodes_duckduckgo_redirect():
    url = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage"
    assert _normalize_result_url(url) == "https://example.com/page"


def test_normalize_result_url_drops_duckduckgo_ads():
    url = (
        "https://duckduckgo.com/y.js?ad_domain=tripadvisor.com&ad_provider=bingv7aa"
        "&ad_type=txad&click_metadata=abc&rut=123"
    )

    assert _normalize_result_url(url) == ""


def test_duckduckgo_parser_extracts_result_title_and_snippet():
    html = """
    <div class="result">
      <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">
        Example Title
      </a>
      <div class="result__snippet">Example snippet text.</div>
    </div>
    """

    parser = _DuckDuckGoResultParser()
    parser.feed(html)

    assert len(parser.results) == 1
    assert parser.results[0]["title"] == "Example Title"
    assert parser.results[0]["url"] == "https://example.com"
    assert "Example snippet" in parser.results[0]["snippet"]


def test_duckduckgo_parser_skips_ad_click_links():
    html = """
    <div class="result">
      <a rel="nofollow" class="result__a" href="https://duckduckgo.com/y.js?ad_domain=tripadvisor.com&ad_provider=bingv7aa&ad_type=txad&click_metadata=abc&rut=123">
        Sponsored result
      </a>
      <div class="result__snippet">Ad snippet.</div>
    </div>
    <div class="result">
      <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">
        Example Title
      </a>
      <div class="result__snippet">Example snippet text.</div>
    </div>
    """

    parser = _DuckDuckGoResultParser()
    parser.feed(html)

    assert len(parser.results) == 1
    assert parser.results[0]["title"] == "Example Title"
    assert parser.results[0]["url"] == "https://example.com"


def test_duckduckgo_provider_falls_back_to_lite_on_html_403(monkeypatch):
    provider = DuckDuckGoSearchProvider()

    async def fake_request_text(url: str, *, params=None, headers=None):
        if "html.duckduckgo.com" in url:
            response = type("Resp", (), {"status_code": 403})()
            raise httpx.HTTPStatusError("forbidden", request=None, response=response)
        return """
        <div class="result">
          <a rel="nofollow" class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffamily">
            Family Event
          </a>
          <div class="result-snippet">Great for kids.</div>
        </div>
        """

    monkeypatch.setattr(provider, "_request_text", fake_request_text)

    result = asyncio.run(provider.search("family activities London", max_results=5))

    assert len(result) == 1
    assert result[0]["url"] == "https://example.com/family"
    assert result[0]["title"] == "Family Event"


def test_page_excerpt_extracts_metadata():
    html = """
    <html>
      <head>
        <title>Sample Page</title>
        <meta name="description" content="A short page description.">
      </head>
      <body>
        <p>This is the first paragraph.</p>
        <p>This is the second paragraph.</p>
      </body>
    </html>
    """

    excerpt = _page_excerpt(html)

    assert excerpt["title"] == "Sample Page"
    assert excerpt["description"] == "A short page description."
    assert "first paragraph" in excerpt["excerpt"].lower()


def test_web_search_service_merges_search_and_page_results():
    service = WebSearchService()

    async def fake_search(query: str, max_results: int):
        return [
            {
                "title": "Result One",
                "url": "https://example.com/one",
                "domain": "example.com",
                "snippet": "Snippet one",
                "source": "duckduckgo",
            },
            {
                "title": "Result Two",
                "url": "https://example.com/two",
                "domain": "example.com",
                "snippet": "Snippet two",
                "source": "duckduckgo",
            },
        ][:max_results]

    async def fake_page_summary(url: str):
        return {
            "title": f"Page for {url}",
            "description": "Description",
            "excerpt": "Excerpt",
        }

    service.provider.search = fake_search  # type: ignore[method-assign]
    service._fetch_page_summary = fake_page_summary  # type: ignore[method-assign]

    result = asyncio.run(service.search("latest family news", max_results=2, fetch_pages=True))

    assert result["provider"] == "duckduckgo"
    assert result["query"] == "latest family news"
    assert len(result["results"]) == 2
    assert len(result["pages"]) == 2
    assert result["pages"][0]["page_title"] == "Page for https://example.com/one"


def test_web_search_service_caches_repeated_queries():
    service = WebSearchService()

    call_counts = {"search": 0, "page": 0}

    async def search_calls(query: str, max_results: int):
        call_counts["search"] += 1
        return [
            {
                "title": "Result One",
                "url": "https://example.com/one",
                "domain": "example.com",
                "snippet": "Snippet one",
                "source": "duckduckgo",
            }
        ]

    async def page_calls(url: str):
        call_counts["page"] += 1
        return {
            "title": "Page title",
            "description": "Description",
            "excerpt": "Excerpt",
        }

    service.provider.search = search_calls  # type: ignore[method-assign]
    service._fetch_page_summary = page_calls  # type: ignore[method-assign]

    first = asyncio.run(service.search("latest family news", max_results=1, fetch_pages=True))
    second = asyncio.run(service.search("latest family news", max_results=1, fetch_pages=True))

    assert first["results"][0]["title"] == "Result One"
    assert second["results"][0]["title"] == "Result One"
    assert call_counts["search"] == 1
    assert call_counts["page"] == 1


def test_web_search_service_selects_tavily_when_configured(monkeypatch):
    monkeypatch.setattr("app.services.web_search_service.settings.web_search_provider", "tavily")
    monkeypatch.setattr("app.services.web_search_service.settings.web_search_tavily_api_key", "tvly-test")

    service = WebSearchService()

    assert service.provider_name == "tavily"
    assert isinstance(service.provider, TavilySearchProvider)


def test_web_search_provider_auto_uses_tavily_with_key(monkeypatch):
    monkeypatch.setattr("app.services.web_search_providers.settings.web_search_provider", "auto")
    monkeypatch.setattr("app.services.web_search_providers.settings.web_search_tavily_api_key", "tvly-test")

    resolved = resolve_web_search_provider()

    assert resolved.name == "tavily"
    assert isinstance(resolved.provider, TavilySearchProvider)


def test_web_search_provider_auto_falls_back_without_tavily_key(monkeypatch):
    monkeypatch.setattr("app.services.web_search_providers.settings.web_search_provider", "auto")
    monkeypatch.setattr("app.services.web_search_providers.settings.web_search_tavily_api_key", "")

    resolved = resolve_web_search_provider()

    assert resolved.name == "duckduckgo"
    assert isinstance(resolved.provider, DuckDuckGoSearchProvider)


def test_tavily_provider_normalizes_results(monkeypatch):
    monkeypatch.setattr("app.services.web_search_providers.settings.web_search_tavily_api_key", "tvly-test")
    monkeypatch.setattr("app.services.web_search_providers.settings.web_search_tavily_search_depth", "advanced")

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": "Tavily Result",
                        "url": "https://example.com/tavily",
                        "content": "Relevant content",
                        "score": 0.9,
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.services.web_search_providers.httpx.AsyncClient", FakeClient)

    provider = TavilySearchProvider()
    result = asyncio.run(provider.search("latest family news", max_results=1))

    assert captured["url"] == "https://api.tavily.com/search"
    assert captured["json"]["query"] == "latest family news"
    assert captured["json"]["search_depth"] == "advanced"
    assert result[0]["source"] == "tavily"
    assert result[0]["title"] == "Tavily Result"
