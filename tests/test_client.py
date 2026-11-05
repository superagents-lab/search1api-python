import asyncio
import json
from pathlib import Path

import httpx
import pytest

from search1api import (
    AsyncSearch1API,
    AuthenticationError,
    InternalServerError,
    Search1API,
    Search1APIConfigurationError,
)


def json_response(status_code, body, request):
    return httpx.Response(status_code, json=body, request=request)


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("SEARCH1API_API_KEY", raising=False)
    with pytest.raises(Search1APIConfigurationError):
        Search1API()


@pytest.mark.parametrize("method", ["search", "news"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_preserves_nested_metadata(method, asynchronous):
    body = {
        "searchParameters": {"query": "q"},
        "results": [
            {
                "title": "Thread",
                "link": "https://example.com/thread",
                "snippet": "Discussion",
                "published_date": "2026-10-12",
                "metadata": {"num_comments": 0},
            }
        ],
    }
    transport = httpx.MockTransport(lambda request: json_response(200, body, request))

    async def run():
        async with httpx.AsyncClient(transport=transport) as http_client:
            async with AsyncSearch1API("test-key", client=http_client) as client:
                return await getattr(client, method)("q")

    if asynchronous:
        response = asyncio.run(run())
    else:
        with httpx.Client(transport=transport) as http_client:
            with Search1API("test-key", client=http_client) as client:
                response = getattr(client, method)("q")
    assert response == body
    assert response["results"][0]["metadata"]["num_comments"] == 0
    assert "num_comments" not in response["results"][0]


def test_rejects_invalid_retry_and_timeout_settings():
    with pytest.raises(Search1APIConfigurationError, match="max_retries"):
        Search1API("test-key", max_retries=-1)
    with pytest.raises(Search1APIConfigurationError, match="timeout"):
        Search1API("test-key", timeout=0)
    with pytest.raises(Search1APIConfigurationError, match="retry_delay"):
        Search1API("test-key", retry_delay=-1)


def test_search_maps_parameters_and_authentication():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(
            200,
            {
                "searchParameters": {
                    "query": "agent sdk",
                    "max_results": 3,
                    "crawl_results": 0,
                    "image": False,
                    "include_sites": [],
                    "exclude_sites": [],
                },
                "results": [],
            },
            request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client)

    client.search(
        "agent sdk",
        search_service="google",
        max_results=3,
        include_sites=["search1api.com"],
    )

    assert len(seen) == 1
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert json.loads(seen[0].content) == {
        "query": "agent sdk",
        "search_service": "google",
        "max_results": 3,
        "include_sites": ["search1api.com"],
    }
    http_client.close()


def test_screenshot_returns_bytes_and_response_metadata():
    seen = []
    image = b"\x89PNG"

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            content=image,
            headers={
                "Content-Type": "image/png",
                "X-Request-Id": "req_screenshot_1",
            },
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client)

    result = client.screenshot(
        "https://example.com",
        full_page=True,
        viewport={"width": 1280, "height": 720, "device_scale_factor": 2},
        wait_until="networkidle",
    )

    assert result == {
        "data": image,
        "content_type": "image/png",
        "request_id": "req_screenshot_1",
    }
    assert seen[0].headers["accept"] == "image/png"
    assert json.loads(seen[0].content) == {
        "url": "https://example.com",
        "full_page": True,
        "viewport": {
            "width": 1280,
            "height": 720,
            "device_scale_factor": 2,
        },
        "wait_until": "networkidle",
    }
    http_client.close()


def test_authentication_errors_are_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(401, {"message": "Invalid API key"}, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("bad-key", client=http_client, max_retries=2)

    with pytest.raises(AuthenticationError) as exc_info:
        client.usage()

    assert exc_info.value.status_code == 401
    assert calls == 1
    http_client.close()


def test_rate_limits_are_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return json_response(429, {"message": "slow down"}, request)
        return json_response(
            200,
            {
                "usage": 99,
                "user_id": "user_1",
                "credential_type": "api_key",
                "client_id": None,
            },
            request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client, max_retries=1, retry_delay=0)

    assert client.usage()["usage"] == 99
    assert calls == 2
    http_client.close()


def test_deepcrawl_starts_and_polls():
    responses = [
        (202, {"taskId": "task_1", "status": "queued"}),
        (200, {"taskId": "task_1", "status": "processing"}),
        (
            200,
            {
                "taskId": "task_1",
                "status": "completed",
                "success": True,
                "zipUrl": "https://example.com/result.zip",
            },
        ),
    ]

    def handler(request):
        status, body = responses.pop(0)
        return json_response(status, body, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client)

    result = client.deepcrawl(
        "https://example.com", type="all", poll_interval=0, timeout=1
    )

    assert result["success"] is True
    assert responses == []
    http_client.close()


def test_deepcrawl_task_creation_is_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return json_response(502, {"message": "temporary failure"}, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client, max_retries=2, retry_delay=0)

    with pytest.raises(InternalServerError, match="temporary failure"):
        client.start_deepcrawl("https://example.com")

    assert calls == 1
    http_client.close()


DEEPCRAWL_JSON_RESULT = {
    "taskId": "task_2",
    "status": "completed",
    "success": True,
    "format": "json",
    "stats": {"discovered": 12, "matched": 4, "skipped": 1, "crawled": 2, "failed": 1},
    "failed": [{"url": "https://example.com/docs/broken", "error": "HTTP 404"}],
    "resultUrl": "https://example.com/result.json",
    "pages": [
        {"url": "https://example.com/docs", "title": "Docs", "content": "# Docs"},
        {"url": "https://example.com/docs/api", "title": None, "content": "API"},
    ],
}


def test_deepcrawl_sends_scope_and_json_format():
    seen = []
    responses = [
        (202, {"taskId": "task_2", "status": "queued"}),
        (200, DEEPCRAWL_JSON_RESULT),
    ]

    def handler(request):
        seen.append(request)
        status, body = responses.pop(0)
        return json_response(status, body, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client)

    result = client.deepcrawl(
        "https://example.com",
        max_pages=3,
        include_paths=["/docs"],
        exclude_paths=["/docs/internal/*"],
        format="json",
        poll_interval=0,
        timeout=1,
    )

    assert result == DEEPCRAWL_JSON_RESULT
    assert [page["url"] for page in result["pages"]] == [
        "https://example.com/docs",
        "https://example.com/docs/api",
    ]
    assert result["stats"]["skipped"] == 1
    assert str(seen[0].url) == "https://api.search1api.com/deepcrawl"
    assert json.loads(seen[0].content) == {
        "url": "https://example.com",
        "max_pages": 3,
        "include_paths": ["/docs"],
        "exclude_paths": ["/docs/internal/*"],
        "format": "json",
    }
    assert str(seen[1].url) == "https://api.search1api.com/deepcrawl/status/task_2"
    http_client.close()


def test_start_deepcrawl_sends_only_set_fields():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return json_response(202, {"taskId": "task_3", "status": "queued"}, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client)

    client.start_deepcrawl("https://example.com")
    client.start_deepcrawl("https://example.com", type="sitemap", max_pages=1)

    assert seen == [
        {"url": "https://example.com"},
        {"url": "https://example.com", "type": "sitemap", "max_pages": 1},
    ]
    http_client.close()


def test_async_deepcrawl_sends_scope_and_json_format():
    async def run():
        seen = []
        responses = [
            (202, {"taskId": "task_2", "status": "queued"}),
            (200, {"taskId": "task_2", "status": "processing"}),
            (200, DEEPCRAWL_JSON_RESULT),
        ]

        async def handler(request):
            seen.append(request)
            status, body = responses.pop(0)
            return json_response(status, body, request)

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncSearch1API("test-key", client=http_client)
        try:
            result = await client.deepcrawl(
                "https://example.com",
                type="all",
                max_pages=3,
                include_paths=["/docs"],
                exclude_paths=["/docs/internal/*"],
                format="json",
                poll_interval=0,
                timeout=1,
            )
        finally:
            await http_client.aclose()

        assert result["pages"][1]["title"] is None
        assert result["failed"] == DEEPCRAWL_JSON_RESULT["failed"]
        assert result["resultUrl"] == "https://example.com/result.json"
        assert json.loads(seen[0].content) == {
            "url": "https://example.com",
            "type": "all",
            "max_pages": 3,
            "include_paths": ["/docs"],
            "exclude_paths": ["/docs/internal/*"],
            "format": "json",
        }
        assert responses == []

    asyncio.run(run())


def test_search_sends_page_and_new_engines():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return json_response(200, {"results": []}, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client)

    client.search("kubernetes", search_service="bingcn", page=2)
    client.search("Alan Turing", search_service="grokipedia")

    assert bodies == [
        {"query": "kubernetes", "search_service": "bingcn", "page": 2},
        {"query": "Alan Turing", "search_service": "grokipedia"},
    ]
    http_client.close()


def test_ask_sends_only_the_query_with_a_longer_timeout():
    seen = []
    body = {
        "query": "recent papers on speculative decoding",
        "intent": {
            "search_query": "speculative decoding",
            "sources": ["arxiv"],
            "time_range": None,
        },
        "results": [
            {
                "title": "Speculative decoding survey",
                "link": "https://arxiv.org/abs/1",
                "snippet": "Survey",
                "source": "arxiv",
                "relevance": 0.88,
            }
        ],
        "errors": [],
    }

    def handler(request):
        seen.append(request)
        return json_response(200, body, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client)

    assert client.ask(body["query"]) == body
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.search1api.com/ask"
    assert json.loads(request.content) == {"query": body["query"]}
    assert request.extensions["timeout"]["read"] == 45.0
    http_client.close()


def test_maps_sends_location_and_paging():
    seen = []
    body = {
        "searchParameters": {
            "query": "coffee shops",
            "country": "us",
            "language": "en",
            "location": {"latitude": 40.7455, "longitude": -74.0083, "zoom": 15},
            "page": 2,
            "max_results": 5,
        },
        "results": [
            {
                "position": 21,
                "name": "Example Coffee",
                "place_id": "ChIJ123",
                "maps_url": "https://www.google.com/maps/search/?api=1&query=Example",
                "rating": 4.6,
            }
        ],
    }

    def handler(request):
        seen.append(request)
        return json_response(200, body, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client)

    response = client.maps(
        "coffee shops",
        location={"latitude": 40.7455, "longitude": -74.0083, "zoom": 15},
        page=2,
        max_results=5,
    )

    assert response == body
    assert str(seen[0].url) == "https://api.search1api.com/maps"
    assert json.loads(seen[0].content) == {
        "query": "coffee shops",
        "location": {"latitude": 40.7455, "longitude": -74.0083, "zoom": 15},
        "page": 2,
        "max_results": 5,
    }
    http_client.close()


def test_async_maps():
    async def run():
        async def handler(request):
            assert json.loads(request.content) == {"query": "ramen", "country": "jp"}
            return json_response(
                200,
                {
                    "searchParameters": {
                        "query": "ramen",
                        "country": "jp",
                        "language": "en",
                        "page": 1,
                        "max_results": 20,
                    },
                    "results": [],
                },
                request,
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncSearch1API("test-key", client=http_client)
        try:
            assert (await client.maps("ramen", country="jp"))["results"] == []
        finally:
            await http_client.aclose()

    asyncio.run(run())


def test_feedback_is_sent_once_without_retries():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return json_response(503, {"ok": False, "message": "unavailable"}, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = Search1API("test-key", client=http_client, max_retries=2, retry_delay=0)

    with pytest.raises(InternalServerError, match="unavailable"):
        client.feedback(
            "Need publication dates",
            category="feature_request",
            request_id="req_1",
            agent={"name": "codex"},
        )

    assert calls == [
        {
            "message": "Need publication dates",
            "category": "feature_request",
            "request_id": "req_1",
            "agent": {"name": "codex"},
        }
    ]
    http_client.close()


def test_async_ask_and_feedback():
    async def run():
        paths = []

        async def handler(request):
            paths.append(request.url.path)
            if request.url.path == "/feedback":
                return json_response(201, {"id": "fb_1", "status": "new"}, request)
            return json_response(
                200,
                {
                    "query": "q",
                    "intent": {"search_query": "q", "sources": [], "time_range": None},
                    "results": [],
                    "errors": [],
                },
                request,
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncSearch1API("test-key", client=http_client)
        try:
            assert (await client.ask("q"))["results"] == []
            assert await client.feedback("docs typo") == {"id": "fb_1", "status": "new"}
        finally:
            await http_client.aclose()
        assert paths == ["/ask", "/feedback"]

    asyncio.run(run())


def test_async_client_uses_the_same_api_shape():
    async def run():
        async def handler(request):
            return json_response(
                200,
                {
                    "usage": 42,
                    "user_id": "user_1",
                    "credential_type": "api_key",
                    "client_id": None,
                },
                request,
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncSearch1API("test-key", client=http_client)
        try:
            response = await client.usage()
            assert response["usage"] == 42
        finally:
            await http_client.aclose()

    asyncio.run(run())


def test_sdk_covers_every_public_openapi_operation():
    contract_path = (
        Path(__file__).resolve().parents[1] / "openapi" / "search1api.openapi.json"
    )
    contract = json.loads(contract_path.read_text())
    operation_ids = sorted(
        operation["operationId"]
        for path in contract["paths"].values()
        for operation in path.values()
    )

    operation_methods = {
        "ask": "ask",
        "crawl": "crawl",
        "deepcrawl": "start_deepcrawl",
        "deepcrawlStatus": "get_deepcrawl_status",
        "extract": "extract",
        "feedback": "feedback",
        "health": "health",
        "maps": "maps",
        "news": "news",
        "search": "search",
        "screenshot": "screenshot",
        "sitemap": "sitemap",
        "trending": "trending",
        "usage": "usage",
    }

    assert operation_ids == sorted(operation_methods)
    for method in operation_methods.values():
        assert callable(getattr(Search1API, method))
        assert callable(getattr(AsyncSearch1API, method))
