# Changelog

## 0.6.0 - 2026-11-05

Adds keyword arguments to `start_deepcrawl` and `deepcrawl` on `Search1API` and `AsyncSearch1API`: `max_pages` (1-1000, default 1000, applied after the path rules in discovery order), `include_paths` and `exclude_paths` (up to 20 URL path rules each; a rule without `*` is a path prefix on segment boundaries, a rule with `*` matches the whole path; exclusion wins) and `format` (`"zip"`, the default, or `"json"`). Unset arguments are not sent. `DeepcrawlStatusResponse` adds `format`, `stats` (`discovered`, `matched`, `skipped`, `crawled`, `failed`), `failed` (`url`, `error`) and, for `format="json"`, `resultUrl` and `pages` (`url`, `title`, Markdown `content`; omitted above 5 MB, use `resultUrl`). Still 20 credits per task. The bundled OpenAPI snapshot is re-synced with the live contract.

## 0.5.0 - 2026-11-03

Adds `maps(query, ...)` on `Search1API` and `AsyncSearch1API` for `POST /maps`: one Google Maps page of up to 20 places with name, place ID and Maps link, plus address, phone, website, rating, review count, coordinates and opening hours when available. Keyword arguments: `country`, `language`, `location` (`latitude`, `longitude`, optional `zoom`), `page` (1-6, pages after the first need `location`) and `max_results`. 3 credits per completed page; API key or OAuth only. The bundled OpenAPI snapshot also records the 50-item batch limit for search, news and crawl.

## 0.4.0 - 2026-10-12

Breaking: search/news engine-specific fields move from each result's top level to optional `metadata` (`kind`, `stars`, `language`, `num_comments`, `points`, `story_url`). Read e.g. `result.metadata.stars` instead of `result.stars`. `published_date` stays at the top level. No legacy field aliases.
