# Search1API Python SDK

Official synchronous and asynchronous Python clients for Search1API.

API documentation: [search1api.com/docs](https://s1.dev/docs)

## Install

```bash
pip install search1api
```

## Search

```python
from search1api import Search1API

client = Search1API()  # reads SEARCH1API_API_KEY
response = client.search(
    "latest AI agent frameworks",
    max_results=10,
    crawl_results=3,
)

for result in response["results"]:
    print(result["title"], result["link"])
```

`search_service` selects one engine (`google` by default), for example `bing`,
`bingcn`, `yandex`, `reddit`, `github`, `arxiv`, `wikipedia`, or `grokipedia`.
`page` requests a later results page on engines with native pagination
(`bing`, `bingcn`, `baidu`, `grokipedia`). Results carry `published_date` when the source
exposes one.

Use the client as a context manager when it owns the HTTP connection pool:

```python
with Search1API("your-api-key") as client:
    print(client.usage())
```

## Async

```python
from search1api import AsyncSearch1API

async with AsyncSearch1API() as client:
    response = await client.search("latest AI agent frameworks")
```

## Ask

`ask` sends a natural-language request and lets Search1API choose the engines
and time window. It returns at most 10 results ranked by relevance, and
`intent` reports what was searched:

```python
answer = client.ask("What are developers saying about Bun 1.3 this month?")

print(answer["intent"]["sources"], answer["intent"]["time_range"])
for result in answer["results"]:
    print(result["relevance"], result["source"], result["title"], result["link"])
```

A completed request costs 5 credits. Ask is not available with pay-per-request
payments, and its default timeout is 45 seconds. Use `search` when you already
know which engine and keywords you want.

## Deepcrawl

`deepcrawl` starts a task and waits for it to finish:

```python
result = client.deepcrawl("https://example.com", type="all")
print(result["zipUrl"])
```

Use `start_deepcrawl`, `get_deepcrawl_status`, and `wait_for_deepcrawl` when
the application needs to control persistence or polling itself.

## Screenshot

Screenshot responses are binary image bytes rather than JSON:

```python
from pathlib import Path

screenshot = client.screenshot(
    "https://example.com",
    format="png",
    full_page=True,
)

Path("screenshot.png").write_bytes(screenshot["data"])
print(screenshot["content_type"], screenshot.get("request_id"))
```

The clients also support news, crawl, sitemap, trending, extract, usage, and
batch operations exposed by the Search1API HTTP API. Requests time out after
30 seconds and retry `429` and transient `5xx` responses twice by default.
Authentication, payment, and validation errors are never retried. Deepcrawl
task creation and feedback are not retried automatically because they are not
idempotent.

## Feedback

`feedback` reports a Search1API problem, missing capability, or confusing
documentation. It is free. Do not include credentials or personal data:

```python
client.feedback(
    "Results for this query have no publication dates",
    category="feature_request",
    request_id="the x-search1api-request-id of the original request",
)
```

## Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy src/search1api
pytest
python -m build
```

The checked-in OpenAPI snapshot is used to verify that the client covers every
public operation.

## License

MIT
