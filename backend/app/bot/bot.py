from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from app.bot.handlers import (
    basic,
    documents,
    expenses,
    group_router,
    private_router,
    trip_admin,
)
from app.config import get_settings

_PRIVATE_COMMAND_SPECS: tuple[tuple[str, str], ...] = (
    ("start", "Начать"),
    ("help", "Помощь"),
    ("app", "Открыть Mini App"),
    ("mytrips", "Мои поездки"),
    ("balance", "Кто кому должен"),
    ("members", "Участники поездки"),
)

_GROUP_COMMAND_SPECS: tuple[tuple[str, str], ...] = (
    ("help", "Как пользоваться"),
    ("newtrip", "Создать поездку"),
    ("join", "Присоединиться к поездке"),
    ("members", "Участники поездки"),
    ("balance", "Кто кому должен"),
    ("app", "История и аналитика"),
)


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


def build_private_commands() -> list[BotCommand]:
    return [BotCommand(command=cmd, description=desc) for cmd, desc in _PRIVATE_COMMAND_SPECS]


def build_group_commands() -> list[BotCommand]:
    return [BotCommand(command=cmd, description=desc) for cmd, desc in _GROUP_COMMAND_SPECS]


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        build_private_commands(),
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        build_group_commands(),
        scope=BotCommandScopeAllGroupChats(),
    )
