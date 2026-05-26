"""Единая точка обработки intent после очистки текста.

Принимает уже очищенный текст (без mention/trigger), отдаёт его
AIProvider, и роутит результат:
- add_expense → confirmation flow (через expenses.propose_expense_from_intent)
- show_balance → BalanceService + сообщение
- show_today_spending → ExpenseService.today_summary
- convert_currency → CurrencyService
- find_document → DocumentService
- get_weather → WeatherService (Open-Meteo, бесплатно)
- unknown → conversational AI
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
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

_MONTHS_RU_TO_NUM: dict[str, int] = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

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
def _strip_city_noise(city: str) -> str:
    """Strip trailing time-window phrases from extracted location text."""
    city = (city or "").strip().rstrip("?!,.")
    patterns = [
        r"\s+(?:на|за)\s*\d{1,2}\s*(?:дн(?:я|ей|и)?|day|days)\s*$",
        r"\s+(?:на|за)\s+недел[юи]\s*$",
        r"\s+(?:на|за)\s+выходн(?:ые|ых)\s*$",
        r"\s+(?:на|за)\s*\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+\d{4})?\s*$",
        r"\s+(?:сегодня|завтра)\s*$",
    ]
    prev = None
    while city and city != prev:
        prev = city
        for pat in patterns:
            city = re.sub(pat, "", city, flags=re.IGNORECASE).strip().rstrip("?!,.")
    return city


def _canonicalize_weather_query(raw_location: str) -> str:
    """Build safe geocoder query without case-conversion heuristics.

    Case fallbacks are handled in weather_service via candidate retries.
    """
    query = (raw_location or "").strip()
    query = re.sub(r"^[,.\s]+|[,.\s]+$", "", query)
    query = re.sub(r"\s+", " ", query)
    return query


def _extract_weather_location(text: str) -> tuple[str | None, str | None]:
    """Extract (location_query, location_surface) from weather request text.

    - location_query: neutral place string for API lookup
    - location_surface: user-friendly phrase with preposition (e.g. "в Стамбуле", "на Бали")
    """
    raw = (text or "").strip()

    preposition_pattern = re.compile(
        r"(?:погод[аыуе]?|weather|сколько\s+градусов|температур[аы]|(?:какая\s+)?погода|(?:какой\s+)?дождь)\s+"
        r"(в|во|на)\s+([A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9\s\-]{1,60})",
        re.IGNORECASE,
    )
    m = preposition_pattern.search(raw)
    if m:
        prep = m.group(1).lower()
        loc_raw = _strip_city_noise(m.group(2))
        if loc_raw:
            surface = f"{prep} {loc_raw}"
            query = _canonicalize_weather_query(loc_raw)
            return (query or loc_raw), surface

    no_prep_pattern = re.compile(
        r"(?:погод[аыуе]?|weather|сколько\s+градусов|температур[аы]|(?:какая\s+)?погода|(?:какой\s+)?дождь)\s+"
        r"([A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9\s\-]{1,60})",
        re.IGNORECASE,
    )
    m2 = no_prep_pattern.search(raw)
    if m2:
        loc_raw = _strip_city_noise(m2.group(1))
        if loc_raw:
            query = _canonicalize_weather_query(loc_raw)
            return (query or loc_raw), None

    return None, None


def _extract_weather_city(text: str) -> str | None:
    """Backward-compatible wrapper for weather city extraction."""
    query, _surface = _extract_weather_location(text)
    return query


def _extract_weather_days(text: str) -> int | None:
    lower = text.lower()
    if re.search(r"(?:на|за)\s+недел[юи]\b", lower):
        return 7
    if re.search(r"(?:на|за)\s+выходн(?:ые|ых)\b", lower):
        return 2

    m = re.search(
        r"(?:на|за)\s*(\d{1,2})\s*(?:дн(?:я|ей|и)?|day|days)\b",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    days = int(m.group(1))
    if days <= 0:
        return None
    return days


def _is_weekend_request(text: str) -> bool:
    return bool(re.search(r"(?:на|за)\s+выходн(?:ые|ых)\b", text.lower()))


def _extract_weather_target_date(text: str) -> tuple[date | None, bool]:
    lower = text.lower()
    if "сегодня" in lower:
        return date.today(), True
    if "завтра" in lower:
        return date.today() + timedelta(days=1), False

    m = re.search(
        r"(?:на|за)\s*(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
        r"(?:\s+(\d{4}))?",
        lower,
        re.IGNORECASE,
    )
    if not m:
        return None, False

    day_num = int(m.group(1))
    month_name = m.group(2).lower()
    month_num = _MONTHS_RU_TO_NUM.get(month_name)
    if month_num is None:
        return None, False

    year_raw = m.group(3)
    today = date.today()
    year = int(year_raw) if year_raw else today.year
    try:
        target = date(year, month_num, day_num)
    except ValueError:
        return None, False

    if year_raw is None and target < today:
        try:
            target = date(today.year + 1, month_num, day_num)
        except ValueError:
            return None, False

    return target, False


async def handle_intent_text(
    message: Message,
    text: str,
    *,
    source: str,
    use_reply: bool = False,
) -> bool:
    """Распознать intent и выполнить соответствующее действие.

    Returns True если intent обработан (включая unknown/chat),
    False — если text пустой/None.

    `source`: 'add' | 'ai' | 'expense' | 'mention' | 'reply' | 'trigger' | 'private'.
    """
    if not text or not text.strip():
        return False

    cleaned = text.strip()

    # ── Fast-path: regex pre-check for weather queries ──
    if _WEATHER_RE.search(cleaned):
        location_query, location_surface = _extract_weather_location(cleaned)
        if location_query:
            requested_days = _extract_weather_days(cleaned)
            target_date, today_requested = _extract_weather_target_date(cleaned)
            weekend_requested = _is_weekend_request(cleaned)
            if requested_days and requested_days > 1:
                target_date = None
            logger.info(
                "intent_router fast-path weather location=%s days=%s target_date=%s weekend=%s text=%s",
                location_query,
                requested_days,
                target_date.isoformat() if target_date else None,
                weekend_requested,
                cleaned[:80],
            )
            send = message.reply if use_reply else message.answer
            weather_text = await get_weather(
                location_query,
                target_date=target_date,
                days=requested_days,
                today_requested=today_requested,
                location_surface=location_surface,
                weekend_requested=weekend_requested,
            )
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
            await send(
                "В этом чате пока нет поездки.\n\n"
                "Создайте её командой:\n"
                "<code>/newtrip</code>\n\n"
                "После этого участники смогут нажать /join."
            )
            return
        balances = await BalanceService(session).calculate_balances(trip.id)
        transfers = simplify_debts(balances)
        members = await TripService(session).get_members(trip.id)

    if not balances:
        await send(f"<b>{trip.title}</b>: расходов пока нет.")
        return

    name_by_id = {m.user_id: (m.display_name or f"участник {m.user_id}") for m in members}
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
            await send(
                "В этом чате пока нет поездки.\n\n"
                "Создайте её командой:\n"
                "<code>/newtrip</code>\n\n"
                "После этого участники смогут нажать /join."
            )
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
            await send(
                "В этом чате пока нет поездки.\n\n"
                "Создайте её командой:\n"
                "<code>/newtrip</code>\n\n"
                "После этого участники смогут нажать /join."
            )
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
