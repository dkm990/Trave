"""Безопасные стартап-диагностики.

Формирует короткий отчёт о ключевых параметрах конфигурации без раскрытия секретов
(токенов, паролей в DSN). Используется и FastAPI lifespan, и run_bot.py.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.config import get_settings


def _db_kind(database_url: str) -> str:
    if not database_url:
        return "unknown"
    if database_url.startswith("sqlite"):
        return "sqlite"
    if "postgres" in database_url:
        return "postgres"
    if "mysql" in database_url:
        return "mysql"
    return "other"


def _safe_url(url: str) -> str:
    """URL без user:password, чтобы не светить секреты в логах."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.password or parsed.username:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            return parsed._replace(netloc=netloc).geturl()
        return url
    except Exception:  # noqa: BLE001
        return "<unparseable>"


def build_startup_report(component: str) -> dict[str, Any]:
    settings = get_settings()
    return {
        "component": component,
        "app_env": settings.app_env,
        "app_timezone": settings.app_timezone,
        "database": {
            "kind": _db_kind(settings.database_url),
            "url_safe": _safe_url(settings.database_url),
        },
        "telegram": {
            "bot_token_set": bool(settings.telegram_bot_token),
            "bot_username_set": bool(settings.telegram_bot_username),
            "mini_app_url_set": bool(
                settings.mini_app_url and settings.mini_app_url != "https://example.com"
            ),
            "mini_app_url": settings.mini_app_url,
        },
        "auth": {
            "dev_allow_insecure": bool(settings.dev_allow_insecure_auth),
        },
        "currency": {
            "providers": ["frankfurter", "exchangerate_open"],
            "primary": "frankfurter",
            "fallback": "exchangerate_open",
            "frankfurter_url": settings.frankfurter_base_url,
            "cache_ttl_hours": settings.currency_cache_ttl_hours,
            "default_base_currency": settings.default_base_currency,
        },
        "ai": {
            "provider": settings.ai_provider,
            "fallback_provider": settings.ai_fallback_provider,
            "gemini_api_key_set": bool(settings.gemini_api_key),
            "gemini_model": settings.gemini_model,
            "gemini_timeout_seconds": settings.gemini_timeout_seconds,
            "gemini_retry_count": settings.gemini_retry_count,
            "gemini_use_context_cache": settings.gemini_use_context_cache,
            "ollama_url": settings.ollama_base_url if settings.ai_provider == "ollama" else None,
            "ollama_model": settings.ollama_model if settings.ai_provider == "ollama" else None,
        },
    }


def log_startup_report(component: str, logger: logging.Logger | None = None) -> None:
    log = logger or logging.getLogger(__name__)
    report = build_startup_report(component)
    tg = report["telegram"]
    auth = report["auth"]
    db = report["database"]
    cur = report["currency"]
    ai = report["ai"]
    log.info("== Yo %s startup ==", component)
    log.info("env=%s", report["app_env"])
    log.info("database: %s (%s)", db["kind"], db["url_safe"])
    log.info(
        "telegram: bot_token=%s bot_username=%s mini_app=%s",
        "set" if tg["bot_token_set"] else "MISSING",
        "set" if tg["bot_username_set"] else "missing",
        "set" if tg["mini_app_url_set"] else "MISSING (https tunnel?)",
    )
    log.info(
        "auth: dev_allow_insecure=%s%s",
        auth["dev_allow_insecure"],
        " (DO NOT USE IN PROD)" if auth["dev_allow_insecure"] else "",
    )
    log.info(
        "currency: providers=%s base=%s ttl=%sh",
        ",".join(cur["providers"]),
        cur["default_base_currency"],
        cur["cache_ttl_hours"],
    )
    log.info(
        "ai: provider=%s fallback=%s gemini_key=%s model=%s",
        ai["provider"],
        ai["fallback_provider"],
        "set" if ai["gemini_api_key_set"] else "missing",
        ai["gemini_model"],
    )
    if not tg["bot_token_set"]:
        log.warning("TELEGRAM_BOT_TOKEN is empty — bot will fail to start.")
    if not tg["mini_app_url_set"]:
        log.warning("MINI_APP_URL is empty/default — Mini App button won't work.")
