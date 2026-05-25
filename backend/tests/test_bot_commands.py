from __future__ import annotations

import pytest
from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from app.bot.bot import build_group_commands, build_private_commands, setup_bot_commands


def _as_pairs(commands):
    return [(c.command, c.description) for c in commands]


def test_private_commands_match_expected():
    assert _as_pairs(build_private_commands()) == [
        ("start", "Начать"),
        ("help", "Помощь"),
        ("app", "Открыть Mini App"),
        ("mytrips", "Мои поездки"),
        ("balance", "Кто кому должен"),
        ("members", "Участники поездки"),
    ]


def test_group_commands_match_expected():
    assert _as_pairs(build_group_commands()) == [
        ("help", "Как пользоваться"),
        ("newtrip", "Создать поездку"),
        ("join", "Присоединиться к поездке"),
        ("members", "Участники поездки"),
        ("balance", "Кто кому должен"),
        ("app", "История и аналитика"),
    ]


def test_advanced_commands_not_visible():
    visible = {c.command for c in build_private_commands()} | {
        c.command for c in build_group_commands()
    }
    hidden = {
        "rename",
        "setlocalcurrency",
        "setdisplaycurrency",
        "summary",
        "trips",
        "bindtrip",
    }
    assert visible.isdisjoint(hidden)


@pytest.mark.asyncio
async def test_setup_bot_commands_sets_private_and_group_scopes():
    calls = []

    class _Bot:
        async def set_my_commands(self, commands, scope):
            calls.append((commands, scope))

    await setup_bot_commands(_Bot())

    assert len(calls) == 2
    assert isinstance(calls[0][1], BotCommandScopeAllPrivateChats)
    assert isinstance(calls[1][1], BotCommandScopeAllGroupChats)
    assert _as_pairs(calls[0][0]) == _as_pairs(build_private_commands())
    assert _as_pairs(calls[1][0]) == _as_pairs(build_group_commands())
