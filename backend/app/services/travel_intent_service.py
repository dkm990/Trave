from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_INTENTS = {"weather", "expense", "travel_advice", "casual_chat", "unknown"}
ALLOWED_PERIOD_TYPES = {"today", "tomorrow", "exact_date", "days", "week", "weekend", None}

SYSTEM_INSTRUCTION = """Ты extractor intent для Telegram travel bot.
Твоя задача: извлечь intent и параметры из текста. НИКОГДА не выдумывай факты.
Верни строго один JSON без markdown и без пояснений.

Схема:
{
  "intent": "weather|expense|travel_advice|casual_chat|unknown",
  "confidence": 0.0,
  "weather": {
    "location": "string|null",
    "location_surface": "string|null",
    "period_type": "today|tomorrow|exact_date|days|week|weekend|null",
    "date_text": "string|null",
    "days": 0
  },
  "expense": {
    "amount": 0,
    "currency": "string|null",
    "description": "string|null",
    "participants_text": "string|null"
  }
}

Правила:
- Погода: извлеки только параметры запроса. Не генерируй прогноз.
- Если запрос о погоде и есть предлог в локации, сохрани natural form в location_surface:
  "в Стамбуле", "на Бали", "в Москве".
- location: каноничный запрос для API (без предлога, без хвостов периода), если можно.
- period_type:
  - "сегодня" -> today
  - "завтра" -> tomorrow
  - "на 4 июня" -> exact_date и date_text="4 июня"
  - "на 4 дня" -> days и days=4
  - "на неделю" -> week и days=7
  - "на выходные" -> weekend
- Если не хватает данных (например, нет location), intent всё равно weather, но confidence ниже.
- Расходы: извлекай только простые поля expense.
- Если не уверен, ставь intent=unknown и понижай confidence.
"""


@dataclass
class TravelWeatherIntent:
    location: str | None = None
    location_surface: str | None = None
    period_type: str | None = None
    date_text: str | None = None
    days: int | None = None


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

    @classmethod
    def unknown(cls) -> "TravelIntentResult":
        return cls(intent="unknown", confidence=0.0, weather=TravelWeatherIntent(), expense=TravelExpenseIntent())


class TravelIntentService:
    """LLM-only extraction layer for travel intents.

    This service never produces weather facts and never writes data.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None
        self._client_init_failed = False

    def _init_client(self) -> Any | None:
        if self._client is not None or self._client_init_failed:
            return self._client
        try:
            from google import genai  # type: ignore
        except ImportError:
            self._client_init_failed = True
            logger.warning("google-genai SDK not installed for TravelIntentService")
            return None
        if not self.settings.gemini_api_key:
            self._client_init_failed = True
            return None
        try:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        except Exception as exc:  # noqa: BLE001
            self._client_init_failed = True
            logger.warning("TravelIntentService Gemini init failed: %s", exc)
            return None
        return self._client

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

        client = self._init_client()
        if client is None:
            return TravelIntentResult.unknown()

        prompt = self._build_prompt(
            raw_text=text,
            chat_context=chat_context,
            current_dt=current_dt,
            active_trip_title=active_trip_title,
        )
        attempts = max(1, self.settings.travel_intent_retry_count + 1)
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                raw_json = await asyncio.wait_for(
                    self._call_gemini(client, prompt),
                    timeout=self.settings.travel_intent_timeout_seconds,
                )
                parsed = self._parse_response(raw_json)
                if parsed is not None:
                    return parsed
                last_exc = ValueError("invalid extractor JSON")
            except asyncio.TimeoutError as exc:
                last_exc = exc
                logger.warning("TravelIntentService timeout attempt=%s", attempt + 1)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "TravelIntentService error attempt=%s type=%s msg=%s",
                    attempt + 1,
                    type(exc).__name__,
                    str(exc)[:200],
                )
                msg = str(exc).lower()
                if any(marker in msg for marker in ("429", "503", "resource_exhausted", "unavailable")):
                    break

        logger.warning("TravelIntentService fallback to unknown: %s", last_exc)
        return TravelIntentResult.unknown()

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

        weather = self._parse_weather(payload.get("weather"))
        expense = self._parse_expense(payload.get("expense"))
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

        location = self._norm_text(payload.get("location"))
        location_surface = self._norm_text(payload.get("location_surface"))
        date_text = self._norm_text(payload.get("date_text"))
        return TravelWeatherIntent(
            location=location,
            location_surface=location_surface,
            period_type=period_type,
            date_text=date_text,
            days=days,
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
