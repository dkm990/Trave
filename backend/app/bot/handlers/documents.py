from __future__ import annotations

import uuid
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.session import session_scope
from app.services.document_service import (
    DocumentInput,
    DocumentService,
    SensitiveDocumentRefused,
)
from app.services.trip_service import TripService
from app.services.user_service import UserService

router = Router(name="documents")


DOC_TYPES = [
    ("ticket", "🎫 Билет"),
    ("hotel_booking", "🏨 Отель"),
    ("insurance", "🛡 Страховка"),
    ("itinerary", "🗺 Маршрут"),
    ("voucher", "🎁 Ваучер"),
    ("other", "📄 Другое"),
]


@dataclass
class PendingDoc:
    user_id: int
    chat_id: int
    file_id: str
    file_unique_id: str | None
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    suggested_title: str
    visibility: str


_PENDING_DOCS: dict[str, PendingDoc] = {}


@dataclass
class PendingDocPick:
    user_id: int
    chat_id: int
    query_text: str | None


_PENDING_DOC_PICKS: dict[str, PendingDocPick] = {}


def _build_doc_kb(pid: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, label in DOC_TYPES:
        row.append(InlineKeyboardButton(text=label, callback_data=f"doc:type:{pid}:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"doc:cancel:{pid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.document | F.photo)
async def on_file(message: Message):
    file_id: str
    file_unique_id: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None

    if message.document:
        file_id = message.document.file_id
        file_unique_id = message.document.file_unique_id
        file_name = message.document.file_name
        mime_type = message.document.mime_type
        file_size = message.document.file_size
    elif message.photo:
        # Telegram присылает несколько размеров; берём самое большое
        photo = message.photo[-1]
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        mime_type = "image/jpeg"
        file_size = photo.file_size
    else:
        return

    if message.chat.type != "private":
        # В группе документы личного характера — не сохраняем без явной команды
        return

    title_hint = file_name or message.caption or "Документ"
    pid = uuid.uuid4().hex[:10]
    _PENDING_DOCS[pid] = PendingDoc(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name=file_name,
        mime_type=mime_type,
        file_size=file_size,
        suggested_title=title_hint,
        visibility="private",
    )
    await message.answer(
        "Сохранить как документ поездки?\n\n"
        "<b>Важно</b>: в MVP мы не храним паспорта, визы и документы с чувствительными данными. "
        "Сохраняйте только билеты, брони, страховки, маршруты и ваучеры.\n\n"
        "Выбери тип:",
        reply_markup=_build_doc_kb(pid),
    )


@router.callback_query(F.data.startswith("doc:cancel:"))
async def doc_cancel(query: CallbackQuery):
    pid = query.data.split(":", 2)[2]
    _PENDING_DOCS.pop(pid, None)
    await query.message.edit_text("Отменено.")
    await query.answer()


@router.callback_query(F.data.startswith("doc:type:"))
async def doc_type_selected(query: CallbackQuery):
    parts = query.data.split(":")
    if len(parts) < 4:
        await query.answer("Bad payload")
        return
    pid, doc_type = parts[2], parts[3]
    pending = _PENDING_DOCS.get(pid)
    if not pending:
        await query.answer("Запрос устарел", show_alert=True)
        return
    if query.from_user.id != pending.user_id:
        await query.answer("Это не ваш документ", show_alert=True)
        return

    async with session_scope() as session:
        user = await UserService(session).get_or_create(
            telegram_user_id=pending.user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name,
        )
        trips = await TripService(session).list_user_trips(user.id)
        if not trips:
            _PENDING_DOCS.pop(pid, None)
            await query.message.edit_text(
                "Нет активной поездки. Создай: /newtrip Название"
            )
            await query.answer()
            return
        trip = trips[0]
        try:
            doc = await DocumentService(session).save(
                DocumentInput(
                    trip_id=trip.id,
                    owner_user_id=user.id,
                    title=pending.suggested_title,
                    doc_type=doc_type,
                    telegram_file_id=pending.file_id,
                    telegram_file_unique_id=pending.file_unique_id,
                    file_name=pending.file_name,
                    mime_type=pending.mime_type,
                    file_size=pending.file_size,
                    visibility=pending.visibility,
                )
            )
        except SensitiveDocumentRefused as exc:
            _PENDING_DOCS.pop(pid, None)
            await query.message.edit_text(str(exc))
            await query.answer()
            return

    _PENDING_DOCS.pop(pid, None)
    await query.message.edit_text(
        f"✅ Сохранено в поездке <b>{trip.title}</b>: «{doc.title}» (тип: {doc.doc_type})"
    )
    await query.answer()


@router.message(Command("docs"))
async def cmd_docs(message: Message):
    query_text = (message.text or "").partition(" ")[2].strip() or None
    in_group = message.chat.type in ("group", "supergroup")

    async with session_scope() as session:
        user = await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        if in_group:
            trip = await TripService(session).get_trip_for_chat(message.chat.id)
            if not trip:
                await message.answer("Поездка не найдена.")
                return
        else:
            trips = await TripService(session).list_user_trips(user.id)
            if not trips:
                await message.answer("Нет поездок. Создай: /newtrip Название")
                return
            if len(trips) == 1:
                trip = trips[0]
            else:
                # Multiple trips — ask user to pick one via inline keyboard
                pick_id = uuid.uuid4().hex[:10]
                _PENDING_DOC_PICKS[pick_id] = PendingDocPick(
                    user_id=message.from_user.id,
                    chat_id=message.chat.id,
                    query_text=query_text,
                )
                rows: list[list[InlineKeyboardButton]] = []
                row: list[InlineKeyboardButton] = []
                for t in trips:
                    row.append(InlineKeyboardButton(
                        text=t.title,
                        callback_data=f"docs:trip:{t.id}:{pick_id}",
                    ))
                    if len(row) == 2:
                        rows.append(row)
                        row = []
                if row:
                    rows.append(row)
                await message.answer(
                    "Выбери поездку:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                )
                return

        docs = await DocumentService(session).list_for_trip(
            trip_id=trip.id,
            viewer_user_id=user.id,
            query=query_text,
        )

    if in_group:
        # В общем чате не светим личные документы
        shared = [d for d in docs if d.visibility == "shared"]
        if not shared:
            await message.reply("Общих документов поездки нет. Я могу прислать твои личные в личку.")
            personal = [d for d in docs if d.visibility != "shared"]
            if personal:
                try:
                    await _send_doc_list(message.bot, message.from_user.id, trip.title, personal)
                    await message.reply("Отправил тебе в личку.")
                except Exception:
                    await message.reply("Не смог написать в личку — открой со мной диалог и нажми /start.")
            return
        await _send_doc_list(message.bot, message.chat.id, trip.title, shared)
        return

    if not docs:
        await message.answer("Документов нет.")
        return
    await _send_doc_list(message.bot, message.chat.id, trip.title, docs)


@router.callback_query(F.data.startswith("docs:trip:"))
async def docs_trip_selected(query: CallbackQuery):
    """Handle trip selection for /docs when user has multiple trips."""
    parts = query.data.split(":")
    if len(parts) < 4:
        await query.answer("Bad payload")
        return
    trip_id_str, pick_id = parts[2], parts[3]
    pending = _PENDING_DOC_PICKS.pop(pick_id, None)
    if not pending:
        await query.answer("Запрос устарел", show_alert=True)
        return
    if query.from_user.id != pending.user_id:
        await query.answer("Это не ваша команда", show_alert=True)
        return

    try:
        trip_id = int(trip_id_str)
    except (TypeError, ValueError):
        await query.answer("Bad payload")
        return

    async with session_scope() as session:
        user = await UserService(session).get_or_create(
            telegram_user_id=pending.user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name,
        )
        trip = await TripService(session).get_trip(trip_id)
        if not trip:
            await query.message.edit_text("Поездка не найдена.")
            await query.answer()
            return
        docs = await DocumentService(session).list_for_trip(
            trip_id=trip.id,
            viewer_user_id=user.id,
            query=pending.query_text,
        )

    if not docs:
        await query.message.edit_text("Документов нет.")
        await query.answer()
        return
    await query.message.edit_text(f"<b>Документы поездки {trip.title}</b>")
    await _send_doc_list(query.bot, pending.chat_id, trip.title, docs)
    await query.answer()


async def _send_doc_list(bot, chat_id: int, trip_title: str, docs):
    lines = [f"<b>Документы поездки {trip_title}</b>"]
    for d in docs:
        lines.append(f"• [{d.doc_type}] {d.title} (id {d.id})")
    await bot.send_message(chat_id, "\n".join(lines))
    # Отправляем сами файлы
    for d in docs:
        try:
            if d.mime_type and d.mime_type.startswith("image/"):
                await bot.send_photo(chat_id, d.telegram_file_id, caption=d.title)
            else:
                await bot.send_document(chat_id, d.telegram_file_id, caption=d.title)
        except Exception:
            continue
