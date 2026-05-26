from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # Telegram. Поддерживаем оба имени переменной: BOT_TOKEN и TELEGRAM_BOT_TOKEN.
    telegram_bot_token: str = Field(
        default="",
        validation_alias=AliasChoices("BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
    )
    telegram_bot_username: str = Field(
        default="",
        validation_alias=AliasChoices("BOT_USERNAME", "TELEGRAM_BOT_USERNAME"),
    )
    mini_app_url: str = Field(
        default="https://example.com",
        validation_alias=AliasChoices("WEBAPP_URL", "MINI_APP_URL"),
    )

    # App
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    dev_allow_insecure_auth: bool = True

    # Database
    database_url: str = "sqlite+aiosqlite:///./yo.db"

    # Currency
    currency_provider: str = "frankfurter"
    frankfurter_base_url: str = "https://api.frankfurter.dev/v1"
    currency_cache_ttl_hours: int = 12
    default_base_currency: str = "RUB"
    exchangerate_api_key: str = ""

    # Flights
    flight_provider: str = "mock"
    aerodatabox_api_key: str = ""
    aerodatabox_api_host: str = "aerodatabox.p.rapidapi.com"
    flight_provider_cache_ttl_seconds: int = 300
    flight_refresh_min_seconds: int = 600

    # AI
    ai_provider: str = "rule_based"
    ai_fallback_provider: str = "rule_based"

    # Timezone для today summary (IANA name). Fallback на UTC.
    app_timezone: str = "UTC"

    # Ollama (legacy)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Gemini
    gemini_api_key: Optional[str] = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 8
    gemini_retry_count: int = 1
    gemini_use_context_cache: bool = False
    enable_travel_intent_extractor: bool = False
    travel_intent_timeout_seconds: int = 5
    # retries count (0 = single attempt)
    travel_intent_retry_count: int = 0

    # CORS
    cors_origins: str = "*"

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Test helper: clears cache so env changes take effect."""
    get_settings.cache_clear()  # type: ignore[attr-defined]
    return get_settings()
