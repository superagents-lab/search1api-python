# Search1API Python SDK

Official synchronous and asynchronous Python clients for Search1API.

API documentation: [search1api.com/docs](https://www.search1api.com/docs)

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
task creation is not retried automatically because it is not idempotent.

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
