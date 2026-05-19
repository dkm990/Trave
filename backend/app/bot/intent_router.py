"""Единая точка обработки intent после очистки текста.

Принимает уже очищенный текст (без mention/trigger), отдаёт его
AIProvider, и роутит результат:
- add_expense → confirmation flow (через expenses.propose_expense_from_intent)
- show_balance → BalanceService + сообщение
- show_today_spending → ExpenseService.today_summary
- convert_currency → CurrencyService
- find_document → DocumentService
- get_weather → WeatherService (Open-Meteo, бесплатно)
- unknown → подсказка с примерами
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from aiogram.types import Message

from app.ai import get_ai_provider
from app.ai.base import Intent
from app.bot.session import session_scope
from app.services.balance_service import BalanceService, simplify_debts
from app.services.currency_service import CurrencyError, CurrencyService
from app.services.document_service import DocumentService
from app.services.expense_service import ExpenseService
from app.services.formatting import format_dual, format_money
from app.services.trip_service import TripService
from app.services.user_service import UserService
from app.services.weather_service import get_weather

if TYPE_CHECKING:
    from app.models.trip import Trip

logger = logging.getLogger(__name__)

# Regex for fast weather query detection (before AI parsing)
# NOTE: no trailing \b because Cyrillic word boundaries work differently
_WEATHER_RE = re.compile(
    r"(?:погод|weather|сколько\s+градусов|температур|дождь|снег|ветер|влажность)",
    re.IGNORECASE,
)

# ── City name noise stripping ──
# After the broad city capture regex extracts \"CityName + noise\", these
# patterns strip trailing time/noise phrases. Applied iteratively because
# compound phrases like \"на ближайшие 10 дней\" need multiple passes.
_CITY_NOISE_PATTERNS: list[re.Pattern] = [
    # Compound phrases (longest/most specific first)
    re.compile(
        r"\s+(?:на|за|в|к)\s+ближайш(?:ие|ий|ую|ее|его)\s+\d+\s*"
        r"(?:дн(?:я|ей|и)|день)?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+(?:на|за|в|к)\s+"
        r"(?:\d+\s*(?:дн(?:я|ей|и)|день|недел[юьи]))\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+(?:на|за|в|к)\s+(?:выходны[ех]|выходные)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+(?:на|за|в|к)\s+"
        r"(?:ближайш(?:ие|ий|ую|ее|его)|сегодня|завтра)\s*$",
        re.IGNORECASE,
    ),
    # Time words at end (without preposition)
    re.compile(r"\s+(?:сегодня|завтра|недел[юи])\s*$", re.IGNORECASE),
    # Generic \"на/за/в + anything\" at end
    re.compile(r"\s+(?:на|за|в|к)\s+.+?\s*$", re.IGNORECASE),
    # Trailing orphan preposition (leftover after earlier strip)
    re.compile(r"\s+(?:на|за|в|к)\s*$", re.IGNORECASE),
]

# Russian prepositional → nominative case fixes for geocoding.
# Order matters: specific patterns before general ones.
_CASE_FIXES: list[tuple[re.Pattern, str]] = [
    # -ии → -ия (России→Россия, Турции→Турция)
    (re.compile(r"ии$"), "ия"),
    # -ае → -ай (Дубае→Дубай)
    (re.compile(r"ае$"), "ай"),
    # -ве → -ва where stem ends in consonant (Москве→Москва)
    (re.compile(r"([гжзклмнпрстфхцчшщбвд])ве$"), r"\1ва"),
    # Foreign city: hard consonant + е → drop е (Париже→Париж, Берлине→Берлин)
    (re.compile(r"([бгджзклмнпрстфхцчшщ])е$"), r"\1"),
    # -ле/-ре/-не → drop е (Стамбуле→Стамбул, Барселоне→Барселон)
    (re.compile(r"([лрн])е$"), r"\1"),
]


def _strip_city_noise(city: str) -> str:
    """Iteratively strip trailing noise phrases from extracted city name."""
    prev = None
    while prev != city:
        prev = city
        for pat in _CITY_NOISE_PATTERNS:
            city = pat.sub("", city).strip().rstrip("?!,.")
    return city


def _normalize_city_case(city: str) -> str:
    """Normalize Russian prepositional case → nominative for geocoding."""
    for pattern, replacement in _CASE_FIXES:
        city = pattern.sub(replacement, city)
    return city


def _extract_weather_city(text: str) -> str | None:
    """Extract city name from a weather query.

    Uses a broad regex to capture the city + surrounding text,
    then strips common noise phrases (\"на ближайшие 10 дней\", etc.)
    and normalises Russian prepositional case → nominative.
    """
    # Broad city capture — includes digits so \"10 дней\" doesn't break matching
    broad_city = re.compile(
        r"(?:погод[аыуе]?\s+(?:в|на|во)\s+|weather\s+(?:in|at)\s+|"
        r"сколько\s+градусов\s+(?:в|на|во)\s+|"
        r"температур[аы]\s+(?:в|на|во)\s+|"
        r"(?:какая\s+)?погода\s+(?:в|на|во)\s+|"
        r"(?:какой\s+)?дождь\s+(?:в|на|во)\s+)"
        r"([A-ZА-ЯЁ][A-Za-zА-Яа-яёЁ0-9\s\-]+?)(?:\?|$)",
        re.IGNORECASE,
    )
    m = broad_city.search(text)
    if m:
        city = m.group(1).strip().rstrip("?!")
        city = _strip_city_noise(city)
        city = _normalize_city_case(city)
        if city:
            return city

    # Fallback: look for \"погода CityName\" at end
    fallback = re.search(
        r"(?:погод[аыуе]?|weather)\s+"
        r"([A-ZА-ЯЁ][A-Za-zА-Яа-яёЁ\s\-]{2,30})\s*$",
        text,
        re.IGNORECASE,
    )
    if fallback:
        return fallback.group(1).strip().rstrip("?!")

    return None


async def handle_intent_text(
    message: Message,
    text: str,
    *,
    source: str,
    use_reply: bool = False,
) -> bool:
    """Распознать intent и выполнить соответствующее действие.

    Returns True если intent обработан (даже unknown с подсказкой),
    False — если text пустой/None.

    `source`: 'add' | 'ai' | 'expense' | 'mention' | 'reply' | 'trigger' | 'private'.
    """
    if not text or not text.strip():
        return False

    cleaned = text.strip()

    # ── Fast-path: regex pre-check for weather queries ──
    if _WEATHER_RE.search(cleaned):
        city = _extract_weather_city(cleaned)
        if city:
            logger.info(
                "intent_router fast-path weather city=%s text=%s", city, cleaned[:80]
            )
            send = message.reply if use_reply else message.answer
            weather_text = await get_weather(city)
            await send(weather_text)
            return True

    intent = await get_ai_provider().parse_intent(cleaned)

    logger.info(
        "intent_router chat=%s user=%s source=%s text_len=%s "
        "provider=%s intent=%s confidence=%.2f needs_confirmation=%s",
        message.chat.id,
        message.from_user.id if message.from_user else None,
        source,
        len(cleaned),
        get_ai_provider().name,
        intent.action,
        intent.confidence,
        intent.needs_confirmation,
    )

    if intent.action == "add_expense":
        from app.bot.handlers.expenses import propose_expense_from_intent

        await propose_expense_from_intent(
            message, intent, source=source, use_reply=use_reply
        )
        return True

    send = message.reply if use_reply else message.answer

    # ── Chat / unknown → conversational AI с памятью группы ──
    if intent.action in ("chat", "unknown"):
        await _chat_response(message, cleaned, send)
        return True

    if intent.action == "show_balance":
        await _show_balance(message, send)
        return True

    if intent.action == "show_today_spending":
        await _show_today_spending(message, send)
        return True

    if intent.action == "convert_currency":
        await _convert_currency(intent, send)
        return True

    if intent.action == "find_document":
        await _find_document(message, intent, send)
        return True

    if intent.action == "get_weather":
        await _handle_get_weather(intent, send)
        return True

    # Unreachable — chat and unknown handled above
    await _chat_response(message, cleaned, send)
    return True


async def _handle_get_weather(intent: Intent, send) -> None:
    """Handle get_weather intent from AI provider."""
    city = (intent.payload.get("city") or "").strip()
    if not city:
        await send("Какой город? Напиши, например, «погода Москва» 🌍")
        return
    weather_text = await get_weather(city)
    await send(weather_text)


async def _chat_response(message: Message, text: str, send) -> None:
    """Conversational AI ответ с памятью группы."""
    from app.ai import get_ai_provider
    from app.services.group_memory_service import GroupMemoryService

    # Собираем контекст: память группы + информация о поездке
    context_parts: list[str] = []

    async with session_scope() as session:
        mem_svc = GroupMemoryService(session)
        memories = await mem_svc.get_recent_memories(message.chat.id)
        if memories:
            context_parts.append(mem_svc.format_memories_for_context(memories))

        trip = await _resolve_active_trip(session, message)
        trip_info = ""
        if trip:
            trip_info = f"Поездка: {trip.title}, валюта: {trip.default_currency}"

    context = "\n\n".join(context_parts) if context_parts else ""

    response = await get_ai_provider().generate_chat_response(
        text, context=context, trip_info=trip_info
    )
    await send(response)


async def _resolve_active_trip(session, message: Message) -> "Trip | None":
    if message.chat.type in ("group", "supergroup"):
        return await TripService(session).get_trip_for_chat(message.chat.id)
    user = await UserService(session).get_or_create(
        telegram_user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    trips = await TripService(session).list_user_trips(user.id)
    return trips[0] if trips else None


async def _show_balance(message: Message, send) -> None:
    async with session_scope() as session:
        trip = await _resolve_active_trip(session, message)
        if not trip:
            await send("Нет активной поездки. /newtrip Название")
            return
        balances = await BalanceService(session).calculate_balances(trip.id)
        transfers = simplify_debts(balances)
        members = await TripService(session).get_members(trip.id)

    if not balances:
        await send(f"<b>{trip.title}</b>: расходов пока нет.")
        return

    name_by_id = {m.user_id: (m.display_name or f"user_{m.user_id}") for m in members}
    cur = trip.default_currency
    bal_lines = "\n".join(
        f"• {name_by_id.get(b.user_id, b.user_id)}: оплатил {format_money(b.paid, cur)}, "
        f"доля {format_money(b.owes, cur)}, баланс {format_money(b.net, cur)}"
        for b in balances
    )
    if transfers:
        t_lines = "\n".join(
            f"→ {name_by_id.get(t.from_user_id, t.from_user_id)} должен "
            f"{name_by_id.get(t.to_user_id, t.to_user_id)} {format_money(t.amount, cur)}"
            for t in transfers
        )
    else:
        t_lines = "Все рассчитались."
    await send(f"<b>{trip.title}</b> · база {cur}\n\n{bal_lines}\n\n{t_lines}")


async def _show_today_spending(message: Message, send) -> None:
    async with session_scope() as session:
        trip = await _resolve_active_trip(session, message)
        if not trip:
            await send("Нет активной поездки. /newtrip Название")
            return
        summary = await ExpenseService(session, CurrencyService(session)).today_summary(
            trip.id
        )
    cur = summary.base_currency or trip.default_currency
    if summary.count == 0:
        await send(f"<b>{trip.title}</b>: сегодня расходов не было.")
        return

    parts: list[str] = []
    originals = summary.by_original_currency
    if len(originals) == 1:
        ((ocur, oamt),) = originals.items()
        head = (
            f"<b>{trip.title}</b> · сегодня потратили: "
            f"{format_dual(oamt, ocur, summary.total, cur)}"
        )
        parts.append(head)
    else:
        parts.append(
            f"<b>{trip.title}</b> · сегодня потратили: {format_money(summary.total, cur)}"
        )
        if originals:
            parts.append("")
            parts.append("<b>В оригинальных валютах:</b>")
            for ocur, oamt in sorted(originals.items(), key=lambda x: -x[1]):
                parts.append(f"• {format_money(oamt, ocur)}")

    if summary.by_category:
        parts.append("")
        parts.append("<b>По категориям:</b>")
        for cat, amount_base in summary.by_category.items():
            cat_originals = summary.by_category_original.get(cat) or {}
            if len(cat_originals) == 1:
                ocur = next(iter(cat_originals))
                oamt = cat_originals[ocur]
                parts.append(
                    f"• {cat}: {format_dual(oamt, ocur, amount_base, cur)}"
                )
            else:
                parts.append(f"• {cat}: {format_money(amount_base, cur)}")

    await send("\n".join(parts))


async def _convert_currency(intent: Intent, send) -> None:
    payload = intent.payload
    try:
        amount = Decimal(str(payload.get("amount", "")))
    except (InvalidOperation, TypeError):
        await send("Не понял сумму. Пример: <code>/rate 100 USD RUB</code>")
        return
    base = (payload.get("from") or "").upper()
    quote = (payload.get("to") or "").upper()
    if not base or not quote:
        await send("Укажи базу и квоту: <code>/rate 100 USD RUB</code>")
        return
    async with session_scope() as session:
        try:
            converted, info = await CurrencyService(session).convert(amount, base, quote)
        except CurrencyError as exc:
            await send(f"Курс недоступен: {exc}")
            return
    age = "из кеша" if info.from_cache else "свежий"
    await send(
        f"<b>{format_money(amount, base)} = {format_money(converted, quote)}</b>\n"
        f"Курс: 1 {base} = {info.rate} {quote}\n"
        f"Дата: {info.rate_date.isoformat()} ({age}, {info.provider})"
    )


async def _find_document(message: Message, intent: Intent, send) -> None:
    query = (intent.payload.get("query") or "").strip()
    doc_type = intent.payload.get("doc_type")
    async with session_scope() as session:
        trip = await _resolve_active_trip(session, message)
        if not trip:
            await send("Нет активной поездки.")
            return
        user = await UserService(session).get_by_telegram_id(message.from_user.id)
        if not user:
            await send("Сначала /start.")
            return
        docs = await DocumentService(session).list_for_trip(
            trip_id=trip.id,
            viewer_user_id=user.id,
            query=query or None,
            doc_type=doc_type,
        )
    if not docs:
        await send("Документов не нашёл.")
        return
    lines = [f"<b>Документы поездки {trip.title}</b>"]
    for d in docs:
        lines.append(f"• [{d.doc_type}] {d.title} (id {d.id})")
    await send("\n".join(lines))
