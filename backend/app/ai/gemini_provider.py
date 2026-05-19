"""GeminiProvider — intent parser через Google Gemini API.

Дизайн:
- Никогда не пишет в БД и не выполняет действий: возвращает только Intent.
- На любую ошибку (timeout, network, 429, 5xx, invalid JSON, validation)
  делает один retry, затем возвращает Intent от fallback-провайдера.
- Системная инструкция компактная и содержит конкретные правила для
  travel-доменных фраз (донги/баксы/кк).
- Не логирует API ключ или полный пользовательский текст.

SDK: google-genai (https://github.com/googleapis/python-genai)
Импорт ленивый — приложение не падает, если SDK не установлен.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.ai.base import KNOWN_ACTIONS, AIProvider, Intent
from app.ai.rule_based import RuleBasedProvider
from app.config import get_settings

logger = logging.getLogger(__name__)


SYSTEM_INSTRUCTION = """Ты parser для Telegram travel bot. На вход короткое сообщение пользователя.
Верни ТОЛЬКО JSON по схеме. Ничего не выполняй сам.

Схема:
{
 "action": "add_expense|show_balance|show_today_spending|convert_currency|find_document|get_weather|unknown",
 "confidence": 0.0-1.0,
 "needs_confirmation": true|false,
 "payload": {...}
}

Правила:
- "за всех" => split_scope=all, split_mode=equal
- "с Зои", "ехали с Зои", "мы с Зои" => split_scope=mentioned, participant_names=["Зои"], split_mode=equal
- Если явного указателя нет (нет "за всех", нет "с X", нет "делим на N") =>
  split_scope=self (только текущий пользователь). НИКОГДА не делать
  автоматический split_scope=all только потому что есть глагол "оплатил".

--- НЕРОВНОЕ ДЕЛЕНИЕ (NEROVNO) ---
Когда пользователь явно указывает РАЗНЫЕ суммы или проценты на каждого:
- "я 400, Зои 600" => split_mode=by_amount, custom_shares=[{"name": "я", "share": "400"}, {"name": "Зои", "share": "600"}]
- "30% я, 70% Зои" => split_mode=by_percent, custom_shares=[{"name": "я", "share": "30"}, {"name": "Зои", "share": "70"}]
- "неровно: 500 с меня, 200 с Зои, 300 с Антона" => split_mode=by_amount, custom_shares с суммами
- "я 250₺, Зои 750₺" => split_mode=by_amount, custom_shares=[{"name": "я", "share": "250"}, ...]
- "я 40%, Зои 60%" => split_mode=by_percent
- Если видишь паттерн «имя + число» / «число + с + имя» / «имя + процент» несколько раз подряд — это неровное деление
- При неровном делении split_scope=mentioned, participant_names НЕ ЗАПОЛНЯЙ (используй custom_shares)
- При неровном делении всё равно ВСЕГДА needs_confirmation=true

--- ПОГОДА (WEATHER) ---
- Запросы о погоде: "какая погода в Москве", "weather in Paris", "сколько градусов в Сочи", "температура в Берлине", "дождь в Питере" => get_weather, payload: {city: "Москва"}
- Извлекай название города в именительном падеже (Москва, Париж, Берлин, а не «в Москве»).
- Если город не указан явно — action=unknown.

--- ВАЛЮТЫ ---
- "баксы", "доллары", "$" => USD
- "донги", "донгов", "vnd", "₫" => VND
- "руб", "рубли", "₽" => RUB
- "лари", "gel" => GEL
- "бат", "баты", "thb" => THB
- "лир", "лиры", "турецких лир", "₺", "TRY" => TRY
- "1.2кк", "1.2kk", "1,2кк" => 1200000
- "50 баксов" => amount="50", currency="USD"
- "ресторан 1.2кк донгов за всех" => add_expense title=ресторан amount=1200000 currency=VND split_scope=all
- "1200 лир за всех" => add_expense amount=1200 currency=TRY split_scope=all
- "₺250 за всех" => add_expense amount=250 currency=TRY split_scope=all
- "я заплатил за такси 50 баксов" (без "за всех", без "с X") =>
  add_expense amount=50 currency=USD split_scope=self
- "скинь баланс", "кто кому должен" => show_balance scope=trip
- "сколько мы потратили за сегодня" => show_today_spending date=today group_by=category
- Если неясно — action=unknown, confidence < 0.5

get_weather.payload: {city: string}
add_expense.payload: {amount: string, currency: string (ISO 3-letter),
 title: string, payer_name: string|null,
 participant_names: list[string]|null,
 split_scope: "all"|"mentioned"|"self"|"unknown",
 split_mode: "equal"|"by_amount"|"by_percent",
 custom_shares: list[{name: string, share: string}]|null,
 category: "food"|"taxi"|"hotel"|"tickets"|"shopping"|"other"|"unknown"}
show_balance.payload: {scope: "trip"}
show_today_spending.payload: {date: "today", group_by: "category"|"none"}
convert_currency.payload: {amount: string, from: string, to: string}
find_document.payload: {query: string, doc_type: string|null}

add_expense ВСЕГДА needs_confirmation=true. chat — needs_confirmation=false.
Остальные read-only — false. Если сообщение не про деньги/расходы — используй action=chat."""


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, fallback: AIProvider | None = None) -> None:
        self.settings = get_settings()
        self.fallback = fallback or RuleBasedProvider()
        self._client: Any | None = None
        self._client_init_failed = False

    def _init_client(self) -> Any | None:
        if self._client is not None or self._client_init_failed:
            return self._client
        try:
            from google import genai  # type: ignore
        except ImportError:
            logger.warning("google-genai SDK not installed; falling back")
            self._client_init_failed = True
            return None
        if not self.settings.gemini_api_key:
            self._client_init_failed = True
            return None
        try:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini client init failed: %s", exc)
            self._client_init_failed = True
            return None
        return self._client

    async def parse_intent(
        self, text: str, *, context: dict | None = None
    ) -> Intent:
        client = self._init_client()
        if client is None:
            return await self.fallback.parse_intent(text, context=context)

        attempts = max(1, self.settings.gemini_retry_count + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                raw_json = await asyncio.wait_for(
                    self._call_gemini(client, text),
                    timeout=self.settings.gemini_timeout_seconds,
                )
                intent = self._parse_response(raw_json, text)
                if intent is not None:
                    return intent
                last_error = ValueError("invalid response shape")
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning("Gemini timeout attempt=%s", attempt + 1)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "Gemini error attempt=%s type=%s msg=%s",
                    attempt + 1,
                    type(exc).__name__,
                    str(exc)[:200],
                )

        logger.warning("Gemini exhausted attempts; using fallback. last=%s", last_error)
        return await self.fallback.parse_intent(text, context=context)

    async def _call_gemini(self, client: Any, text: str) -> str:
        """Вызывает Gemini API и возвращает сырую JSON-строку."""
        from google.genai import types  # type: ignore

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.1,
        )

        def _sync_call() -> str:
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=text,
                config=config,
            )
            payload = getattr(response, "text", None)
            if payload:
                return payload
            try:
                return response.candidates[0].content.parts[0].text
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"empty Gemini response: {exc}") from exc

        return await asyncio.to_thread(_sync_call)

    def _parse_response(self, raw_json: str, original_text: str) -> Intent | None:
        try:
            data = json.loads(raw_json)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None

        action = str(data.get("action", "unknown")).lower()
        if action not in KNOWN_ACTIONS:
            action = "unknown"

        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        if action == "add_expense":
            payload = self._normalize_expense_payload(payload)
            if not payload.get("amount") or not payload.get("currency"):
                return Intent(
                    action="unknown",
                    confidence=0.0,
                    raw_text=original_text,
                )
            needs_confirmation = True
        else:
            needs_confirmation = bool(data.get("needs_confirmation", False))

        return Intent(
            action=action,
            confidence=confidence,
            payload=payload,
            raw_text=original_text,
            needs_confirmation=needs_confirmation,
        )

    @staticmethod
    def _normalize_expense_payload(payload: dict) -> dict:
        out: dict[str, Any] = {}
        amount_raw = payload.get("amount")
        out["amount"] = str(amount_raw).strip() if amount_raw is not None else None
        currency = payload.get("currency")
        out["currency"] = currency.upper().strip() if isinstance(currency, str) else None
        out["title"] = (payload.get("title") or "Расход")[:80]
        out["payer_name"] = payload.get("payer_name")
        names = payload.get("participant_names")
        if isinstance(names, list):
            out["participant_names"] = [str(n).strip() for n in names if n]
        else:
            out["participant_names"] = None
        scope = payload.get("split_scope") or "unknown"
        if scope not in {"all", "mentioned", "self", "unknown"}:
            scope = "unknown"
        out["split_scope"] = scope
        out["split_all"] = scope == "all"
        # --- неровное деление ---
        split_mode = payload.get("split_mode") or "equal"
        if split_mode not in {"equal", "by_amount", "by_percent"}:
            split_mode = "equal"
        out["split_mode"] = split_mode
        custom = payload.get("custom_shares")
        if isinstance(custom, list) and split_mode != "equal":
            parsed = []
            for item in custom:
                if isinstance(item, dict) and item.get("name") and item.get("share"):
                    parsed.append({
                        "name": str(item["name"]).strip(),
                        "share": str(item["share"]).strip(),
                    })
            out["custom_shares"] = parsed if parsed else None
        else:
            out["custom_shares"] = None
        # ---
        cat = payload.get("category") or "unknown"
        if cat not in {"food", "taxi", "hotel", "tickets", "shopping", "other", "unknown"}:
            cat = "unknown"
        out["category"] = cat
        return out

    # ── Conversational AI ──────────────────────────────────────────────

    CHAT_SYSTEM_PROMPT = """Ты — Трейв, дружелюбный travel-ассистент в Telegram-группе друзей.
Ты помогаешь с расходами в поездках, но также можешь просто общаться.

Твой стиль:
- Живой, дружелюбный, с эмодзи 🌍✈️
- Отвечаешь кратко, по делу (1-3 предложения, если не просят больше)
- Используешь «ты» на русском
- Помнишь контекст группы (тебе передаётся память предыдущих обсуждений)
- Если вопрос не про travel/расходы — отвечаешь коротко и переводишь тему

Ты НЕ должен:
- Притворяться человеком. Ты — бот-помощник
- Добавлять расходы без явной команды
- Давать финансовые советы (инвестиции и т.п.)

Ты можешь:
- Отвечать на вопросы о поездках, городах, валютах
- Анализировать расходы группы (если есть доступ к ним)
- Шутить и быть в теме разговора
- Предлагать идеи для путешествий"""

    SUMMARIZE_PROMPT = """Ты анализатор группового чата друзей, которые путешествуют вместе.
Сделай КРАТКОЕ саммари (2-4 предложения) этих сообщений.
Выдели только самое важное:
- Ключевые решения (куда едут, даты, бюджет)
- Важные факты о поездке (отели, билеты, маршруты)
- Расходы (кто что оплатил, суммы)
- Конфликты или разногласия (если есть)

Не включай: бытовые разговоры, приветствия, флуд.
Если ничего важного не было — напиши «Ничего существенного».
Формат: просто текст без JSON."""

    async def generate_chat_response(
        self, text: str, *, context: str = "", trip_info: str = ""
    ) -> str:
        """Генерация conversational ответа."""
        client = self._init_client()
        if client is None:
            return "Я сейчас не могу ответить (Gemini недоступен). Попробуй команду /add или /balance."

        prompt = self.CHAT_SYSTEM_PROMPT
        if context:
            prompt += f"\n\n{context}"
        if trip_info:
            prompt += f"\n\nИнформация о поездке:\n{trip_info}"

        try:
            import asyncio

            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=prompt,
                temperature=0.7,
            )

            def _sync_call() -> str:
                response = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=text,
                    config=config,
                )
                payload = getattr(response, "text", None)
                if payload:
                    return payload
                return response.candidates[0].content.parts[0].text

            result = await asyncio.wait_for(
                asyncio.to_thread(_sync_call),
                timeout=self.settings.gemini_timeout_seconds,
            )
            return result.strip() or "Хм, не знаю что сказать 🤔"
        except Exception as exc:
            logger.warning("Chat response failed: %s", exc)
            return "Что-то я задумался... Спроси ещё раз? 😅"

    async def summarize_conversation(self, messages_text: str) -> str:
        """Саммаризация беседы в 2-4 предложения."""
        client = self._init_client()
        if client is None:
            return ""

        try:
            import asyncio

            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=self.SUMMARIZE_PROMPT,
                temperature=0.3,
            )

            def _sync_call() -> str:
                response = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=messages_text,
                    config=config,
                )
                payload = getattr(response, "text", None)
                if payload:
                    return payload
                return response.candidates[0].content.parts[0].text

            result = await asyncio.wait_for(
                asyncio.to_thread(_sync_call),
                timeout=self.settings.gemini_timeout_seconds,
            )
            return result.strip()
        except Exception as exc:
            logger.warning("Summarization failed: %s", exc)
            return ""
