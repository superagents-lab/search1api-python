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
        "crawl": "crawl",
        "deepcrawl": "start_deepcrawl",
        "deepcrawlStatus": "get_deepcrawl_status",
        "extract": "extract",
        "health": "health",
        "news": "news",
        "search": "search",
        "sitemap": "sitemap",
        "trending": "trending",
        "usage": "usage",
    }

    assert operation_ids == sorted(operation_methods)
    for method in operation_methods.values():
        assert callable(getattr(Search1API, method))
        assert callable(getattr(AsyncSearch1API, method))
    assert not hasattr(Search1API, "screenshot")
    assert not hasattr(AsyncSearch1API, "screenshot")
