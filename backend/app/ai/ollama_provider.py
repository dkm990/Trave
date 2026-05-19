from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.ai.base import AIProvider, Intent
from app.ai.rule_based import RuleBasedProvider
from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты парсер для трэвел-бота. На вход — фраза о расходах/валютах/документах.
Возвращай ТОЛЬКО валидный JSON со схемой:
{"action":"add_expense|show_balance|show_today_spending|convert_currency|find_document|unknown",
 "payload":{...}}
Никакого текста, только JSON. Если не уверен — action "unknown"."""


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, fallback: AIProvider | None = None) -> None:
        self.settings = get_settings()
        self.fallback = fallback or RuleBasedProvider()
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def parse_intent(self, text: str, *, context: dict | None = None) -> Intent:
        try:
            client = await self._http()
            url = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"
            resp = await client.post(
                url,
                json={
                    "model": self.settings.ollama_model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            parsed: dict[str, Any] = json.loads(content)
            action = parsed.get("action", "unknown")
            payload = parsed.get("payload", {}) or {}
            return Intent(
                action=action,
                confidence=float(parsed.get("confidence", 0.6)),
                payload=payload,
                raw_text=text,
                needs_confirmation=action == "add_expense",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama failed, falling back: %s", exc)
            return await self.fallback.parse_intent(text, context=context)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
