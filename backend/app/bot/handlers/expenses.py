from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.ai import get_ai_provider
from app.ai.base import Intent
from app.bot.participant_matcher import (
    MemberView,
    match_participants,
    member_view_from_db,
)
from app.bot.session import session_scope
from app.services.currency_service import CurrencyError, CurrencyService
from app.services.expense_service import ExpenseInput, ExpenseService
from app.services.formatting import format_dual, format_money
from app.services.trip_service import TripService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
router = Router(name="expenses")


@dataclass
class PendingExpense:
    chat_id: int
    from_user_id: int
    trip_id: int
    trip_title: str
    payer_user_id: int
    title: str
    amount: str
    currency: str
    category: str | None = None
    participants: list[int] = field(default_factory=list)
    available: list[tuple[int, str]] = field(default_factory=list)
    state: str = "confirm"  # "confirm" | "picker"
    split_mode: str = "equal"  # "equal" | "by_amount" | "by_percent"
    custom_shares: dict[int, str] | None = None  # user_id -> amount_str


_PENDING: dict[str, PendingExpense] = {}


CATEGORY_LABELS = {
    "food": "еда",
    "taxi": "такси",
    "hotel": "отель",
    "tickets": "билеты",
    "shopping": "покупки",
    "other": "другое",
}


def _category_label(category: str | None, title: str) -> str:
    if category and category != "unknown":
        return CATEGORY_LABELS.get(category, category)
    return title


def _new_pending(
    chat_id: int,
    from_user_id: int,
    trip_id: int,
    trip_title: str,
    payer_user_id: int,
    title: str,
    amount: str,
    currency: str,
    participants: list[int],
    available: list[tuple[int, str]],
    state: str = "confirm",
    category: str | None = None,
    split_mode: str = "equal",
    custom_shares: dict[int, str] | None = None,
) -> str:
    pid = uuid.uuid4().hex[:10]
    _PENDING[pid] = PendingExpense(
        chat_id=chat_id,
        from_user_id=from_user_id,
        trip_id=trip_id,
        trip_title=trip_title,
        payer_user_id=payer_user_id,
        title=title,
        amount=str(amount),
        currency=currency.upper(),
        category=category,
        participants=list(participants),
        available=list(available),
        state=state,
        split_mode=split_mode,
        custom_shares=dict(custom_shares) if custom_shares else None,
    )
    return pid


def store_pending(
    chat_id: int,
    from_user_id: int,
    trip_id: int,
    trip_title: str,
    payer_user_id: int,
    title: str,
    amount: str,
    currency: str,
    participants: list[int],
    category: str | None = None,
) -> str:
    """Совместимый API для legacy code paths."""
    return _new_pending(
        chat_id=chat_id,
        from_user_id=from_user_id,
        trip_id=trip_id,
        trip_title=trip_title,
        payer_user_id=payer_user_id,
        title=title,
        amount=amount,
        currency=currency,
        participants=participants,
        available=[],
        state="confirm",
        category=category,
    )


def build_confirm_kb(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"exp:yes:{pending_id}"),
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"exp:edit:{pending_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"exp:no:{pending_id}"),
            ]
        ]
    )


def build_picker_kb(pending: PendingExpense, pending_id: str) -> InlineKeyboardMarkup:
    selected = set(pending.participants)
    rows: list[list[InlineKeyboardButton]] = []
    for uid, label in pending.available:
        marker = "✅" if uid in selected else "⬜"
        rows.append([
            InlineKeyboardButton(
                text=f"{marker} {label}",
                callback_data=f"exp:tog:{pending_id}:{uid}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="👥 Все", callback_data=f"exp:all:{pending_id}"),
        InlineKeyboardButton(text="🙋 Только я", callback_data=f"exp:me:{pending_id}"),
    ])
    rows.append([
        InlineKeyboardButton(text="✅ Сохранить", callback_data=f"exp:save:{pending_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"exp:no:{pending_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


USAGE_HINT = (
    "Примеры:\n"
    "<code>Трейв, 500 рублей такси</code>\n"
    "<code>Трейв, 1200 TRY ужин на всех</code>\n"
    "<code>Трейв, 30 евро музей с Антоном и Машей</code>\n"
    "<code>Трейв, я оплатил 3000 рублей за отель</code>"
)


def _resolve_participants_with_matcher(
    intent: Intent,
    current_user_id: int,
    members_views: list[MemberView],
) -> tuple[list[int], list[str], list[str], str]:
    """Returns (participant_ids, ambiguous_names, missing_names, mode)."""
    payload = intent.payload
    scope = payload.get("split_scope") or "unknown"
    member_ids = [m.user_id for m in members_views]

    if scope == "all":
        return (member_ids or [current_user_id], [], [], "all")
    if scope == "self":
        return ([current_user_id], [], [], "self")
    if scope == "mentioned":
        names = payload.get("participant_names") or []
        resolved: list[int] = [current_user_id]
        ambiguous: list[str] = []
        missing: list[str] = []
        for name in names:
            cands = match_participants(name, members_views)
            if len(cands) == 1:
                if cands[0].user_id not in resolved:
                    resolved.append(cands[0].user_id)
            elif len(cands) > 1:
                ambiguous.append(name)
            else:
                missing.append(name)
        if ambiguous or missing:
            return (resolved, ambiguous, missing, "mentioned_partial")
        return (resolved, [], [], "mentioned")
    if payload.get("split_all"):
        return (member_ids or [current_user_id], [], [], "all")
    return ([current_user_id], [], [], "self")


async def propose_expense_from_intent(
    message: Message,
    intent: Intent,
    *,
    source: str,
    use_reply: bool = False,
) -> None:
    payload = intent.payload
    send = message.reply if use_reply else message.answer

    if not payload.get("amount"):
        await send(
            "Не понял расход.\n\n"
            "Попробуйте так:\n"
            + USAGE_HINT
        )
        return

    async with session_scope() as session:
        trip = await _resolve_trip(session, message)
        if not trip:
            await send(
                "В этом чате пока нет поездки.\n\n"
                "Создайте её командой:\n"
                "<code>/newtrip</code>\n\n"
                "После этого участники смогут нажать /join."
            )
            return
        user = await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        await TripService(session).add_member(trip, user)
        rows = await TripService(session).get_members_with_users(trip.id)

    members_views = [member_view_from_db(m, u) for m, u in rows]
    name_by_id = {
        v.user_id: (v.display_name or v.first_name or v.username or f"участник {v.user_id}")
        for v in members_views
    }
    name_by_id.setdefault(user.id, user.display_name)

    # --- общее разрешение участников ---
    participants, ambiguous, missing, mode = _resolve_participants_with_matcher(
        intent, user.id, members_views
    )
    available = [(v.user_id, name_by_id[v.user_id]) for v in members_views]

    title = payload.get("title", "Расход")
    amount = payload["amount"]
    currency = payload.get("currency") or trip.default_currency
    if not currency:
        await send("Не удалось определить валюту поездки. Укажи валюту расхода явно.")
        return
    currency = currency.upper()
    category = payload.get("category")

    # --- неровное деление: разрешаем имена в custom_shares ---
    split_mode = payload.get("split_mode", "equal")
    custom_shares_named: list[dict] = payload.get("custom_shares") or []
    custom_shares: dict[int, str] | None = None
    if split_mode in ("by_amount", "by_percent") and custom_shares_named:
        custom_shares = {}
        for cs in custom_shares_named:
            name = cs["name"]
            share = cs["share"]
            if name.lower() in ("я", "мне", "меня", "мой", "i", "me", "my"):
                custom_shares[user.id] = share
            else:
                cands = match_participants(name, members_views)
                if len(cands) == 1:
                    custom_shares[cands[0].user_id] = share
                # если не нашли — пропускаем (не ломаем весь flow)
        if len(custom_shares) < 2:
            # недостаточно данных для неровного деления — откатываемся на equal
            split_mode = "equal"
            custom_shares = None

    # --- mentioned_partial с неровным делением несовместим,
    #     поэтому проверяем custom_shares первыми ---

    if split_mode != "equal" and custom_shares:
        # НЕРОВНОЕ ДЕЛЕНИЕ: используем custom_shares
        participant_ids = list(custom_shares.keys())
        pid = _new_pending(
            chat_id=message.chat.id,
            from_user_id=message.from_user.id,
            trip_id=trip.id,
            trip_title=trip.title,
            payer_user_id=user.id,
            title=title,
            amount=amount,
            currency=currency,
            participants=participant_ids,
            available=available,
            state="confirm",
            category=category,
            split_mode=split_mode,
            custom_shares=custom_shares,
        )
        # Формируем красивое описание долей
        currency_suffix = "" if split_mode == "by_amount" else "%"
        shares_lines = []
        for uid in participant_ids:
            share_val = custom_shares.get(uid, "?")
            display_name = name_by_id.get(uid, f"участник {uid}")
            shares_lines.append(f"  {display_name}: {share_val}{currency_suffix}")
        amount_str = format_money(amount, currency)
        await send(
            f"<b>{amount_str}</b>, {title}, оплатил {user.display_name}.\n"
            f"Неровное деление:\n"
            + "\n".join(shares_lines) +
            f"\n\nДобавить?",
            reply_markup=build_confirm_kb(pid),
        )
        return

    if mode == "mentioned_partial":
        pid = _new_pending(
            chat_id=message.chat.id,
            from_user_id=message.from_user.id,
            trip_id=trip.id,
            trip_title=trip.title,
            payer_user_id=user.id,
            title=title,
            amount=amount,
            currency=currency,
            participants=participants,
            available=available,
            state="picker",
            category=category,
        )
        amount_str = format_money(amount, currency)
        problem_names = ambiguous + missing
        problem_desc = (
            "Нашёл несколько похожих имён" if ambiguous else "Не нашёл этих людей среди участников поездки"
        )
        resolved_participants = _format_participants_compact(participants, name_by_id)
        await send(
            f"<b>{amount_str}</b>, {title}, оплатил {user.display_name}.\n\n"
            f"{problem_desc}: {', '.join(problem_names)}.\n"
            "Проверь, что они нажали /join.\n"
            "Или напиши:\n"
            "<code>Трейв, 1200 рублей ужин на всех</code>\n"
            f"Сейчас в расходе: {resolved_participants}.\n"
            "Можно выбрать участников кнопками ниже.",
            reply_markup=build_picker_kb(_PENDING[pid], pid),
        )
        return

    if not participants:
        participants = [user.id]

    pid = _new_pending(
        chat_id=message.chat.id,
        from_user_id=message.from_user.id,
        trip_id=trip.id,
        trip_title=trip.title,
        payer_user_id=user.id,
        title=title,
        amount=amount,
        currency=currency,
        participants=participants,
        available=available,
        state="confirm",
        category=category,
    )

    if mode == "self" or (len(participants) == 1 and participants[0] == user.id):
        participants_str = f"{user.display_name} (только тебя)"
    else:
        participants_str = _format_participants_compact(participants, name_by_id)
    amount_str = format_money(amount, currency)
    per_person_raw = _per_person_share(amount, len(participants))
    per_person_line = ""
    if per_person_raw:
        per_person_line = f"\nДоля: по {format_money(per_person_raw, currency)}"
    await send(
        _build_confirm_text(
            trip_title=trip.title,
            amount_str=amount_str,
            title=title,
            category=category,
            payer_name=user.display_name,
            participants_str=participants_str,
            per_person_line=per_person_line,
        ),
        reply_markup=build_confirm_kb(pid),
    )


async def propose_expense_from_text(
    message: Message,
    text: str,
    *,
    source: str,
    use_reply: bool = False,
) -> bool:
    intent = await get_ai_provider().parse_intent(text)
    logger.info(
        "expense_proposal chat=%s user=%s source=%s text_len=%s "
        "intent=%s needs_confirmation=%s",
        message.chat.id,
        message.from_user.id if message.from_user else None,
        source,
        len(text),
        intent.action,
        intent.needs_confirmation,
    )
    if intent.action != "add_expense" or not intent.payload.get("amount"):
        return False
    await propose_expense_from_intent(message, intent, source=source, use_reply=use_reply)
    return True


@router.message(Command("add"))
async def cmd_add(message: Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer(
            "Напишите расход после команды. Например: "
            "<code>/add 1200 RUB ужин на всех</code>\n\n" + USAGE_HINT
        )
        return
    from app.bot.intent_router import handle_intent_text

    await handle_intent_text(message, text, source="add")


@router.message(Command("ai"))
async def cmd_ai(message: Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer(
            "Напишите расход после команды. Например: "
            "<code>/ai я оплатил 3000 рублей за отель</code>\n\n"
            + USAGE_HINT
        )
        return
    from app.bot.intent_router import handle_intent_text

    await handle_intent_text(message, text, source="ai")


@router.message(Command("expense"))
async def cmd_expense(message: Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer(
            "Напишите расход после команды. Например: "
            "<code>/expense 200 GEL ужин на всех</code>\n\n" + USAGE_HINT
        )
        return
    from app.bot.intent_router import handle_intent_text

    await handle_intent_text(message, text, source="expense")


def _names_for(pending: PendingExpense) -> dict[int, str]:
    return {uid: label for uid, label in pending.available}


def _format_participants_compact(
    participant_ids: list[int],
    names: dict[int, str],
    *,
    max_visible: int = 2,
) -> str:
    labels = [names.get(uid, str(uid)) for uid in participant_ids]
    if len(labels) <= max_visible:
        return ", ".join(labels)
    visible = ", ".join(labels[:max_visible])
    return f"{visible} и ещё {len(labels) - max_visible}"


def _participants_str(pending: PendingExpense) -> str:
    names = _names_for(pending)
    payer = pending.payer_user_id
    if len(pending.participants) == 1 and pending.participants[0] == payer:
        only = names.get(payer, f"участник {payer}")
        return f"{only} (только ты)"
    return _format_participants_compact(pending.participants, names)


def _per_person_share(amount: str, participants_count: int) -> str | None:
    if participants_count <= 0:
        return None
    try:
        total = Decimal(amount)
    except (InvalidOperation, TypeError):
        return None
    return str((total / Decimal(participants_count)).quantize(Decimal("0.01")))


def _trip_label_line(trip_title: str) -> str:
    return f"<b>{trip_title}</b>\n"


def _build_confirm_text(
    *,
    trip_title: str,
    amount_str: str,
    title: str,
    payer_name: str,
    participants_str: str,
    per_person_line: str,
    category: str | None = None,
) -> str:
    return (
        "Проверь расход:\n\n"
        + f"{title} — <b>{amount_str}</b>\n"
        + f"Оплатил: {payer_name}\n"
        + f"Делим на: {participants_str}"
        + f"{per_person_line}"
    )


def _open_picker_view(pending: PendingExpense, pid: str) -> tuple[str, InlineKeyboardMarkup]:
    names = _names_for(pending)
    payer = names.get(pending.payer_user_id, str(pending.payer_user_id))
    amount_str = format_money(pending.amount, pending.currency)
    body = (
        f"<b>{amount_str}</b>, {pending.title}, оплатил {payer}.\n"
        f"Выбери участников вручную:"
    )
    return body, build_picker_kb(pending, pid)


def _build_success_text(pending: PendingExpense, expense) -> str:
    names = _names_for(pending)
    shares = sorted(expense.shares, key=lambda share: names.get(share.user_id, ""))
    share_lines: list[str] = []
    for share in shares:
        share_name = names.get(share.user_id) or f"участник {share.user_id}"
        share_lines.append(
            f"• {share_name}: {format_money(share.share_amount_base, expense.base_currency)}"
        )
    amount_line = format_dual(
        expense.amount_original,
        expense.currency_original,
        expense.amount_base,
        expense.base_currency,
    )
    payer_name = names.get(pending.payer_user_id) or f"участник {pending.payer_user_id}"
    share_block = ""
    if share_lines:
        unique_shares = {line.split(": ", 1)[1] for line in share_lines}
        if len(unique_shares) == 1:
            share_block = f"Доля: по {next(iter(unique_shares))}"
        else:
            share_block = "Доли:\n" + "\n".join(share_lines)
    return (
        "Добавил расход:\n\n"
        f"{pending.title} — <b>{amount_line}</b>\n"
        f"Оплатил: {payer_name}\n"
        f"Участники: {_participants_str(pending)}\n"
        f"{share_block}\n\n"
        + "\n\nБаланс: /balance"
    )


@router.callback_query(F.data.startswith("exp:"))
async def on_callback(query: CallbackQuery):
    parts = query.data.split(":")
    if len(parts) < 3:
        await query.answer("Не получилось обработать кнопку")
        return
    action = parts[1]
    pid = parts[2]
    extra = parts[3] if len(parts) > 3 else None

    pending = _PENDING.get(pid)
    if not pending:
        await query.answer("Запрос устарел", show_alert=True)
        return

    if query.from_user.id != pending.from_user_id:
        await query.answer("Подтвердить может только автор расхода", show_alert=True)
        return

    if action == "no":
        _PENDING.pop(pid, None)
        await query.message.edit_text("Отменено.")
        await query.answer()
        return

    if action == "edit":
        pending.state = "picker"
        body, kb = _open_picker_view(pending, pid)
        await query.message.edit_text(body, reply_markup=kb)
        await query.answer()
        return

    if action == "tog":
        try:
            uid = int(extra or "0")
        except ValueError:
            await query.answer("Не получилось выбрать участника")
            return
        if uid in pending.participants:
            pending.participants = [x for x in pending.participants if x != uid]
        else:
            pending.participants = pending.participants + [uid]
        _, kb = _open_picker_view(pending, pid)
        await query.message.edit_reply_markup(reply_markup=kb)
        await query.answer()
        return

    if action == "all":
        pending.participants = [uid for uid, _ in pending.available]
        _, kb = _open_picker_view(pending, pid)
        await query.message.edit_reply_markup(reply_markup=kb)
        await query.answer()
        return

    if action == "me":
        pending.participants = [pending.payer_user_id]
        _, kb = _open_picker_view(pending, pid)
        await query.message.edit_reply_markup(reply_markup=kb)
        await query.answer()
        return

    if action == "save":
        if not pending.participants:
            await query.answer("Выбери хотя бы одного", show_alert=True)
            return
        pending.state = "confirm"
        names = _names_for(pending)
        payer = names.get(pending.payer_user_id, str(pending.payer_user_id))
        amount_str = format_money(pending.amount, pending.currency)
        per_person_raw = _per_person_share(pending.amount, len(pending.participants))
        per_person_line = ""
        if per_person_raw:
            per_person_line = (
                f"\nДоля: по {format_money(per_person_raw, pending.currency)}"
            )
        await query.message.edit_text(
            _build_confirm_text(
                trip_title=pending.trip_title,
                amount_str=amount_str,
                title=pending.title,
                category=pending.category,
                payer_name=payer,
                participants_str=_participants_str(pending),
                per_person_line=per_person_line,
            ),
            reply_markup=build_confirm_kb(pid),
        )
        await query.answer()
        return

    if action == "yes":
        try:
            amount = Decimal(pending.amount)
        except InvalidOperation:
            await query.answer("Неверная сумма", show_alert=True)
            _PENDING.pop(pid, None)
            return

        # Подготовка custom_shares для ExpenseInput
        custom_shares_dec: dict[int, Decimal] | None = None
        if pending.split_mode in ("by_amount", "by_percent") and pending.custom_shares:
            try:
                custom_shares_dec = {
                    uid: Decimal(share_str)
                    for uid, share_str in pending.custom_shares.items()
                }
            except (InvalidOperation, TypeError):
                await query.answer("Неверная доля в неровном делении", show_alert=True)
                _PENDING.pop(pid, None)
                return

        async with session_scope() as session:
            currency_svc = CurrencyService(session)
            expense_svc = ExpenseService(session, currency_svc)
            try:
                expense = await expense_svc.add_expense(
                    ExpenseInput(
                        trip_id=pending.trip_id,
                        payer_user_id=pending.payer_user_id,
                        title=pending.title,
                        amount=amount,
                        currency=pending.currency,
                        participant_user_ids=pending.participants,
                        category=pending.category,
                        created_by_user_id=pending.payer_user_id,
                        source="bot",
                        split_mode=pending.split_mode,
                        custom_shares=custom_shares_dec,
                    )
                )
            except CurrencyError as exc:
                await query.message.edit_text("Не удалось обновить курс валюты. Попробуйте позже.")
                _PENDING.pop(pid, None)
                await query.answer()
                return
            except ValueError as exc:
                await query.message.edit_text(f"Не удалось добавить расход: {exc}")
                _PENDING.pop(pid, None)
                await query.answer()
                return

        _PENDING.pop(pid, None)
        await query.message.edit_text(_build_success_text(pending, expense))
        await query.answer()
        return

    await query.answer("Не получилось обработать кнопку")


async def _resolve_trip(session, message: Message):
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
