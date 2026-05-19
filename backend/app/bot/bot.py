from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import (
    basic,
    documents,
    expenses,
    group_router,
    private_router,
    trip_admin,
)
from app.config import get_settings


def build_bot() -> Bot:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Регистрируем основные routers (порядок важен).
    dp.include_router(basic.router)
    dp.include_router(trip_admin.router)
    dp.include_router(documents.router)
    dp.include_router(expenses.router)
    dp.include_router(private_router.router)
    dp.include_router(group_router.router)
    return dp
