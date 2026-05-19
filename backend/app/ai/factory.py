from __future__ import annotations

import logging
from functools import lru_cache

from app.ai.base import AIProvider
from app.ai.rule_based import RuleBasedProvider
from app.config import get_settings

logger = logging.getLogger(__name__)


def _build_fallback(name: str) -> AIProvider:
    name = (name or "rule_based").lower()
    if name == "rule_based":
        return RuleBasedProvider()
    logger.warning("Unknown fallback provider %s, using rule_based", name)
    return RuleBasedProvider()


@lru_cache
def get_ai_provider() -> AIProvider:
    settings = get_settings()
    primary = (settings.ai_provider or "rule_based").lower()

    if primary == "gemini":
        if not settings.gemini_api_key:
            logger.warning(
                "AI_PROVIDER=gemini but GEMINI_API_KEY is empty; using rule_based"
            )
            return RuleBasedProvider()
        try:
            from app.ai.gemini_provider import GeminiProvider

            return GeminiProvider(
                fallback=_build_fallback(settings.ai_fallback_provider)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to init GeminiProvider: %s; using rule_based", exc)
            return RuleBasedProvider()

    if primary == "ollama":
        try:
            from app.ai.ollama_provider import OllamaProvider

            return OllamaProvider(
                fallback=_build_fallback(settings.ai_fallback_provider)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to init OllamaProvider: %s; using rule_based", exc)
            return RuleBasedProvider()

    return RuleBasedProvider()


def reset_ai_provider() -> None:
    """Test helper: сбросить кеш фабрики (после смены env)."""
    get_ai_provider.cache_clear()  # type: ignore[attr-defined]
