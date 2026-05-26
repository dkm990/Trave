from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from app.ai.mimo_provider import MimoProvider
from app.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_INTENTS = {"weather", "expense", "travel_advice", "casual_chat", "unknown"}
ALLOWED_PERIOD_TYPES = {"today", "tomorrow", "exact_date", "days", "week", "weekend", None}
MIN_CONFIDENCE = 0.45

SYSTEM_INSTRUCTION = """Ты — классификатор сообщений Telegram travel bot.
Верни только вызов функции extract_travel_intent или строгий JSON той же схемы.
Не отвечай пользователю.
Не выдумывай погоду, цены или факты.
Слово "Трейв" — это имя бота, игнорируй его при классификации.
Для погоды извлекай только location/period.
Для расходов извлекай amount/currency/description, но backend всё равно валидирует.
Если непонятно — intent=unknown, confidence низкий.
Язык сообщений: русский, возможен транслит/английские города.
Если сообщение спрашивает "погода", "дождь", "температура", "ветер" или "что там по погоде" — это intent=weather.
Если есть город/место и дата/период рядом с погодным вопросом, обязательно извлеки их.

Примеры:
"трейв погода стамбул 4 июня" -> weather, location="Стамбул", period_type="exact_date", date_text="4 июня"
"трейв что там по погоде в Стамбуле на выходных" -> weather, location="Стамбул", location_surface="в Стамбуле", period_type="weekend"
"трейв в москве завтра дождь?" -> weather, location="Москва", location_surface="в москве", period_type="tomorrow", asks_rain=true
"трейв 400 лир такси" -> expense, amount=400, currency="TRY", description="такси"
"трейв чем заняться в Турции?" -> travel_advice
"трейв привет, чем занят?" -> casual_chat
"""


@dataclass
class TravelWeatherIntent:
    location: str | None = None
    location_surface: str | None = None
    period_type: str | None = None
    date_text: str | None = None
    days: int | None = None
    asks_rain: bool | None = None


@dataclass
class TravelExpenseIntent:
    amount: float | None = None
    currency: str | None = None
    description: str | None = None
    participants_text: str | None = None


@dataclass
class TravelIntentResult:
    intent: str = "unknown"
    confidence: float = 0.0
    weather: TravelWeatherIntent | None = None
    expense: TravelExpenseIntent | None = None
    provider: str | None = None

    @classmethod
    def unknown(cls) -> "TravelIntentResult":
        return cls(
            intent="unknown",
            confidence=0.0,
            weather=TravelWeatherIntent(),
            expense=TravelExpenseIntent(),
            provider=None,
        )


class TravelIntentService:
    """LLM-only extraction layer for travel intents."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._gemini_client: Any | None = None
        self._gemini_client_init_failed = False
        self._mimo_provider: MimoProvider | None = None

    def _init_gemini_client(self) -> Any | None:
        if self._gemini_client is not None or self._gemini_client_init_failed:
            return self._gemini_client
        try:
            from google import genai  # type: ignore
        except ImportError:
            self._gemini_client_init_failed = True
            logger.warning("google-genai SDK not installed for TravelIntentService")
            return None
        if not self.settings.gemini_api_key:
            self._gemini_client_init_failed = True
            return None
        try:
            self._gemini_client = genai.Client(api_key=self.settings.gemini_api_key)
        except Exception as exc:  # noqa: BLE001
            self._gemini_client_init_failed = True
            logger.warning("TravelIntentService Gemini init failed: %s", exc)
            return None
        return self._gemini_client

    def _init_mimo_provider(self) -> MimoProvider | None:
        if self._mimo_provider is not None:
            return self._mimo_provider
        if not self.settings.mimo_api_key:
            return None
        self._mimo_provider = MimoProvider(
            api_key=self.settings.mimo_api_key,
            base_url=self.settings.mimo_base_url,
            model=self.settings.mimo_model,
            timeout_seconds=self.settings.mimo_timeout_seconds,
            retry_count=self.settings.mimo_retry_count,
            auth_header=self.settings.mimo_auth_header,
            extraction_mode=self.settings.mimo_extraction_mode,
            max_completion_tokens=self.settings.mimo_max_completion_tokens,
            temperature=self.settings.mimo_temperature,
            top_p=self.settings.mimo_top_p,
        )
        return self._mimo_provider

    def _provider_order(self) -> list[str]:
        raw = (self.settings.travel_intent_provider_order or "").strip()
        order: list[str] = []
        if raw:
            for item in raw.split(","):
                name = item.strip().lower()
                if name in {"mimo", "gemini"} and name not in order:
                    order.append(name)
        if not order:
            order = ["mimo", "gemini"]

        filtered: list[str] = []
        for provider in order:
            if provider == "mimo" and self.settings.mimo_api_key:
                filtered.append(provider)
            elif provider == "gemini" and self.settings.gemini_api_key:
                filtered.append(provider)
        return filtered

    async def extract(
        self,
        raw_text: str,
        *,
        chat_context: str,
        current_dt: datetime,
        active_trip_title: str | None = None,
    ) -> TravelIntentResult:
        text = (raw_text or "").strip()
        if not text:
            return TravelIntentResult.unknown()

        prompt = self._build_prompt(
            raw_text=text,
            chat_context=chat_context,
            current_dt=current_dt,
            active_trip_title=active_trip_title,
        )
        provider_order = self._provider_order()
        if not provider_order:
            logger.warning("TravelIntentService: no configured providers for extraction")
            return TravelIntentResult.unknown()

        best_result: TravelIntentResult | None = None
        last_exc: Exception | None = None

        for provider_name in provider_order:
            started = time.monotonic()
            try:
                raw_json = await self._extract_raw_json(provider_name, prompt)
                parsed = self._parse_response(raw_json)
                if parsed is None:
                    raise ValueError("invalid extractor JSON")
                parsed.provider = provider_name
                latency_ms = int((time.monotonic() - started) * 1000)
                logger.info(
                    "TravelIntentService provider=%s status=ok intent=%s confidence=%.2f latency_ms=%s",
                    provider_name,
                    parsed.intent,
                    parsed.confidence,
                    latency_ms,
                )
                best_result = parsed
                if parsed.intent != "unknown" and parsed.confidence >= MIN_CONFIDENCE:
                    return parsed
                logger.info(
                    "TravelIntentService provider=%s low-confidence/unknown fallback intent=%s confidence=%.2f",
                    provider_name,
                    parsed.intent,
                    parsed.confidence,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                latency_ms = int((time.monotonic() - started) * 1000)
                logger.warning(
                    "TravelIntentService provider=%s status=error type=%s msg=%s latency_ms=%s",
                    provider_name,
                    type(exc).__name__,
                    str(exc)[:220],
                    latency_ms,
                )

        if best_result is not None:
            return best_result
        logger.warning("TravelIntentService fallback to unknown: %s", last_exc)
        return TravelIntentResult.unknown()

    async def _extract_raw_json(self, provider_name: str, prompt: str) -> str:
        if provider_name == "mimo":
            provider = self._init_mimo_provider()
            if provider is None:
                raise RuntimeError("mimo provider is not configured")
            return await provider.generate_json(
                system_instruction=SYSTEM_INSTRUCTION,
                prompt=prompt,
            )
        if provider_name == "gemini":
            client = self._init_gemini_client()
            if client is None:
                raise RuntimeError("gemini provider is not configured")
            attempts = max(1, self.settings.travel_intent_retry_count + 1)
            last_exc: Exception | None = None
            for attempt in range(attempts):
                try:
                    return await asyncio.wait_for(
                        self._call_gemini(client, prompt),
                        timeout=self.settings.travel_intent_timeout_seconds,
                    )
                except asyncio.TimeoutError as exc:
                    last_exc = exc
                    logger.warning("TravelIntentService Gemini timeout attempt=%s", attempt + 1)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    msg = str(exc).lower()
                    if any(marker in msg for marker in ("429", "503", "resource_exhausted", "unavailable")):
                        break
            raise last_exc or RuntimeError("gemini extraction failed")
        raise RuntimeError(f"unknown provider: {provider_name}")

    async def _call_gemini(self, client: Any, prompt: str) -> str:
        from google.genai import types  # type: ignore

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.1,
        )

        def _sync_call() -> str:
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=config,
            )
            payload = getattr(response, "text", None)
            if payload:
                return payload
            return response.candidates[0].content.parts[0].text

        return await asyncio.to_thread(_sync_call)

    @staticmethod
    def _build_prompt(
        *,
        raw_text: str,
        chat_context: str,
        current_dt: datetime,
        active_trip_title: str | None,
    ) -> str:
        trip_info = active_trip_title or ""
        return (
            f"chat_context={chat_context}\n"
            f"current_datetime={current_dt.isoformat()}\n"
            f"active_trip_title={trip_info}\n"
            f"user_text={raw_text}"
        )

    @staticmethod
    def _strip_json_fences(raw_text: str) -> str:
        text = (raw_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def _parse_response(self, raw_json: str) -> TravelIntentResult | None:
        cleaned = self._strip_json_fences(raw_json)
        try:
            payload = json.loads(cleaned)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None

        intent = str(payload.get("intent", "unknown")).lower().strip()
        if intent not in ALLOWED_INTENTS:
            intent = "unknown"

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        weather_payload = payload.get("weather") if isinstance(payload.get("weather"), dict) else payload
        expense_payload = payload.get("expense") if isinstance(payload.get("expense"), dict) else payload
        weather = self._parse_weather(weather_payload)
        expense = self._parse_expense(expense_payload)
        return TravelIntentResult(
            intent=intent,
            confidence=confidence,
            weather=weather,
            expense=expense,
        )

    @staticmethod
    def _norm_text(v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def _parse_weather(self, payload: Any) -> TravelWeatherIntent:
        if not isinstance(payload, dict):
            return TravelWeatherIntent()

        period_type = self._norm_text(payload.get("period_type"))
        if period_type not in ALLOWED_PERIOD_TYPES:
            period_type = None

        days_val = payload.get("days")
        days: int | None
        try:
            days = int(days_val) if days_val is not None else None
        except (TypeError, ValueError):
            days = None
        if days is not None and (days <= 0 or days > 16):
            days = None

        asks_rain_raw = payload.get("asks_rain")
        asks_rain = asks_rain_raw if isinstance(asks_rain_raw, bool) else None
        return TravelWeatherIntent(
            location=self._norm_text(payload.get("location")),
            location_surface=self._norm_text(payload.get("location_surface")),
            period_type=period_type,
            date_text=self._norm_text(payload.get("date_text")),
            days=days,
            asks_rain=asks_rain,
        )

    def _parse_expense(self, payload: Any) -> TravelExpenseIntent:
        if not isinstance(payload, dict):
            return TravelExpenseIntent()

        amount_raw = payload.get("amount")
        amount: float | None
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except (TypeError, ValueError):
            amount = None

        currency = self._norm_text(payload.get("currency"))
        if currency:
            currency = currency.upper()
        return TravelExpenseIntent(
            amount=amount,
            currency=currency,
            description=self._norm_text(payload.get("description")),
            participants_text=self._norm_text(payload.get("participants_text")),
        )


@lru_cache(maxsize=1)
def get_travel_intent_service() -> TravelIntentService:
    return TravelIntentService()
