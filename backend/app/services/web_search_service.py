from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str
    source: str | None = None


class WebSearchService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._cache: dict[str, tuple[float, list[WebSearchResult]]] = {}

    def _cache_get(self, key: str) -> list[WebSearchResult] | None:
        ttl = max(0, int(self.settings.web_search_cache_ttl_seconds))
        if ttl <= 0:
            return None
        item = self._cache.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.time() >= expires_at:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: list[WebSearchResult]) -> None:
        ttl = max(0, int(self.settings.web_search_cache_ttl_seconds))
        if ttl <= 0:
            return
        self._cache[key] = (time.time() + ttl, value)

    async def search(self, query: str) -> list[WebSearchResult]:
        q = (query or "").strip()
        if not q:
            return []
        provider = (self.settings.web_search_provider or "").strip().lower()
        if provider != "tavily":
            logger.warning(
                "web_search provider=%s status=skipped reason=unsupported_provider",
                provider or "unknown",
            )
            return []
        if not self.settings.web_search_api_key:
            logger.warning(
                "web_search provider=tavily status=skipped reason=missing_api_key"
            )
            return []

        cache_key = q.lower()
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.info("web_search provider=tavily status=ok source=cache")
            return cached

        base_url = (self.settings.web_search_base_url or "").rstrip("/")
        if not base_url:
            logger.warning(
                "web_search provider=tavily status=skipped reason=missing_base_url"
            )
            return []
        url = f"{base_url}/search"
        payload = {
            "query": q,
            "max_results": max(1, int(self.settings.web_search_max_results)),
            "search_depth": "basic",
        }
        headers = {
            "Authorization": f"Bearer {self.settings.web_search_api_key}",
            "Content-Type": "application/json",
        }
        timeout = max(1, int(self.settings.web_search_timeout_seconds))
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                logger.warning(
                    "web_search provider=tavily status=error type=http_status code=%s",
                    response.status_code,
                )
                return []
            data = response.json()
            rows = data.get("results")
            if not isinstance(rows, list):
                logger.warning(
                    "web_search provider=tavily status=error type=invalid_format"
                )
                return []
            parsed: list[WebSearchResult] = []
            for item in rows:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                url_val = str(item.get("url") or "").strip()
                snippet = str(item.get("content") or item.get("snippet") or "").strip()
                source = str(item.get("source") or "").strip() or None
                if not (title and url_val):
                    continue
                parsed.append(
                    WebSearchResult(
                        title=title,
                        url=url_val,
                        snippet=snippet,
                        source=source,
                    )
                )
            latency_ms = int((time.monotonic() - started) * 1000)
            if not parsed:
                logger.info(
                    "web_search provider=tavily status=ok results=0 latency_ms=%s",
                    latency_ms,
                )
                return []
            self._cache_set(cache_key, parsed)
            logger.info(
                "web_search provider=tavily status=ok results=%s latency_ms=%s",
                len(parsed),
                latency_ms,
            )
            return parsed
        except (httpx.TimeoutException, TimeoutError) as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.warning(
                "web_search provider=tavily status=error type=%s latency_ms=%s",
                type(exc).__name__,
                latency_ms,
            )
            return []
        except (httpx.RequestError, ValueError, TypeError) as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.warning(
                "web_search provider=tavily status=error type=%s latency_ms=%s",
                type(exc).__name__,
                latency_ms,
            )
            return []
