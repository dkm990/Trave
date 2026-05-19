"""Команды управления поездкой: /setcurrency (alias /setdisplaycurrency),
/setlocalcurrency, /rename, /summary."""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.ai.rule_based import KNOWN_CURRENCY_CODES
from app.bot.session import session_scope
from app.services.balance_service import BalanceService, simplify_debts
from app.services.currency_service import CurrencyError, CurrencyService
from app.services.expense_service import ExpenseService
from app.services.formatting import format_dual, format_money
from app.services.trip_service import TripService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
router = Router(name="trip_admin")


async def _resolve_active_trip(session, message: Message):
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


async def _validate_currency_code(code: str) -> bool:
    code = code.strip().upper()
    if len(code) != 3 or not code.isalpha():
        return False
    if code in KNOWN_CURRENCY_CODES:
        return True
    async with session_scope() as session:
        svc = CurrencyService(session)
        try:
            await svc.get_rate(code, "USD")
            return True
        except CurrencyError:
            return False


@router.message(Command("setdisplaycurrency", "setcurrency"))
async def cmd_setdisplaycurrency(message: Message):
    """Меняет default_currency (валюту расчётов балансов).
    /setcurrency — alias для совместимости.
    Меняется только до первого расхода — иначе нужен пересчёт.
    """
    arg = (message.text or "").partition(" ")[2].strip().upper()
    cmd = (message.text or "").split()[0].lower()
    if not arg:
        await message.answer(
            "Использование: <code>/setdisplaycurrency RUB</code>\n"
            "Это валюта расчётов балансов и долгов.\n\n"
            "Для валюты страны путешествия используй "
            "<code>/setlocalcurrency TRY</code>."
        )
        return
    if not await _validate_currency_code(arg):
        await message.answer(
            f"Не знаю валюту <code>{arg}</code>. Используй ISO 3-letter код "
            "(USD, EUR, RUB, TRY, GEL, THB, VND...)."
        )
        return
    async with session_scope() as session:
        trip = await _resolve_active_trip(session, message)
        if not trip:
            await message.answer("Нет активной поездки. /newtrip Название")
            return
        if await TripService(session).has_expenses(trip.id):
            await message.answer(
                "В поездке уже есть расходы. Валюту расчётов менять нельзя "
                "без пересчёта. Для отображения добавим позже.\n\n"
                "Если хотел сменить валюту страны (для today/итогов) — "
                "используй /setlocalcurrency TRY."
            )
            return
        await TripService(session).set_default_currency(trip, arg)
    note = ""
    if cmd.startswith("/setcurrency"):
        note = (
            "\n\nℹ️ /setcurrency меняет валюту расчётов. Для валюты страны "
            "путешествия используй /setlocalcurrency."
        )
    await message.answer(
        f"✅ Валюта расчётов поездки <b>{trip.title}</b> теперь <b>{arg}</b>. "
        f"Все будущие расходы будут конвертироваться в {arg}.{note}"
    )


@router.message(Command("setlocalcurrency"))
async def cmd_setlocalcurrency(message: Message):
    """Меняет local_currency (валюту страны путешествия).
    Аналитический setting; можно менять в любой момент.
    """
    arg = (message.text or "").partition(" ")[2].strip().upper()
    if not arg:
        await message.answer(
            "Использование: <code>/setlocalcurrency TRY</code>\n"
            "Это валюта страны путешествия. Влияет только на отображение "
            "(today summary / итоги), не на расчёт балансов."
        )
        return
    if not await _validate_currency_code(arg):
        await message.answer(
            f"Не знаю валюту <code>{arg}</code>. Используй ISO 3-letter код."
        )
        return
    async with session_scope() as session:
        trip = await _resolve_active_trip(session, message)
        if not trip:
            await message.answer("Нет активной поездки. /newtrip Название")
            return
        await TripService(session).set_local_currency(trip, arg)
    await message.answer(
        f"✅ Локальная валюта поездки <b>{trip.title}</b> теперь <b>{arg}</b>. "
        f"Это влияет на отображение, не на расчёты."
    )


@router.message(Command("rename"))
async def cmd_rename(message: Message):
    new_title = (message.text or "").partition(" ")[2].strip()
    if not new_title:
        await message.answer("Использование: <code>/rename Турция</code>")
        return
    async with session_scope() as session:
        trip = await _resolve_active_trip(session, message)
        if not trip:
            await message.answer("Нет активной поездки. /newtrip Название")
            return
        old_title = trip.title
        await TripService(session).rename(trip, new_title)
    await message.answer(
        f"✅ Поездка переименована: <b>{old_title}</b> → <b>{new_title}</b>"
    )


@router.message(Command("summary"))
async def cmd_summary(message: Message):
    async with session_scope() as session:
        trip = await _resolve_active_trip(session, message)
        if not trip:
            await message.answer("Нет активной поездки. /newtrip Название")
            return

        currency_svc = CurrencyService(session)
        expense_svc = ExpenseService(session, currency_svc)
        balance_svc = BalanceService(session)
        members = await TripService(session).get_members(trip.id)

        expenses = await expense_svc.list_expenses(trip.id)
        balances = await balance_svc.calculate_balances(trip.id)
        transfers = simplify_debts(balances)

    cur = trip.default_currency
    if not expenses:
        await message.answer(
            f"<b>{trip.title}</b> · база {cur}\n\nРасходов пока нет."
        )
        return

    total = Decimal("0.00")
    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    by_original: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    by_category_original: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0.00"))
    )
    for e in expenses:
        if e.status != "confirmed":
            continue
        total += Decimal(e.amount_base)
        cat = (e.category or "other").lower()
        by_category[cat] += Decimal(e.amount_base)
        ocur = (e.currency_original or "").upper()
        by_original[ocur] += Decimal(e.amount_original)
        by_category_original[cat][ocur] += Decimal(e.amount_original)

    name_by_id = {m.user_id: (m.display_name or f"user_{m.user_id}") for m in members}

    parts: list[str] = []
    parts.append(f"<b>{trip.title}</b> · база {cur}")
    parts.append("")
    if len(by_original) == 1:
        ((ocur, oamt),) = by_original.items()
        parts.append(
            f"<b>Всего потрачено:</b> {format_dual(oamt, ocur, total, cur)}"
        )
    else:
        parts.append(f"<b>Всего потрачено:</b> {format_money(total, cur)}")
        if by_original:
            parts.append("")
            parts.append("<b>В оригинальных валютах:</b>")
            for ocur, oamt in sorted(by_original.items(), key=lambda x: -x[1]):
                parts.append(f"• {format_money(oamt, ocur)}")

    if by_category:
        parts.append("")
        parts.append("<b>По категориям:</b>")
        for cat, amount_base in sorted(by_category.items(), key=lambda x: -x[1]):
            inner = by_category_original.get(cat) or {}
            if len(inner) == 1:
                ocur = next(iter(inner))
                oamt = inner[ocur]
                parts.append(f"• {cat}: {format_dual(oamt, ocur, amount_base, cur)}")
            else:
                parts.append(f"• {cat}: {format_money(amount_base, cur)}")

    if balances:
        paid_lines = [
            f"• {name_by_id.get(b.user_id, b.user_id)}: {format_money(b.paid, cur)}"
            for b in sorted(balances, key=lambda x: -x.paid)
            if b.paid > 0
        ]
        if paid_lines:
            parts.append("")
            parts.append("<b>Кто сколько оплатил:</b>")
            parts.extend(paid_lines)

    if transfers:
        parts.append("")
        parts.append("<b>Кто кому должен:</b>")
        for t in transfers:
            parts.append(
                f"→ {name_by_id.get(t.from_user_id, t.from_user_id)} должен "
                f"{name_by_id.get(t.to_user_id, t.to_user_id)} "
                f"{format_money(t.amount, cur)}"
            )
    elif balances:
        parts.append("")
        parts.append("Все рассчитались.")

    await message.answer("\n".join(parts))
