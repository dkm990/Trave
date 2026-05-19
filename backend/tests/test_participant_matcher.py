"""Tests для participant matching: транслитерация, exact, ambiguous, missing."""
from __future__ import annotations

from app.bot.participant_matcher import (
    MemberView,
    match_participants,
)


ZOE = MemberView(
    user_id=1,
    display_name="Zoe Ramirez",
    first_name="Zoe",
    last_name="Ramirez",
    username="zoe_r",
)
ANTON = MemberView(
    user_id=2,
    display_name="Антон",
    first_name="Антон",
    username="anton",
)
NASTYA = MemberView(
    user_id=3,
    display_name="Настя",
    first_name="Настя",
)
ZOEY_DUPLICATE = MemberView(
    user_id=4,
    display_name="Zoe Smith",
    first_name="Zoe",
    last_name="Smith",
)


def test_match_zoi_finds_zoe():
    res = match_participants("Зои", [ZOE, ANTON])
    assert len(res) == 1
    assert res[0].user_id == ZOE.user_id


def test_match_lower_zoi():
    res = match_participants("зои", [ZOE, ANTON])
    assert [r.user_id for r in res] == [ZOE.user_id]


def test_match_zoya_finds_zoe():
    res = match_participants("Зоя", [ZOE, ANTON])
    assert [r.user_id for r in res] == [ZOE.user_id]


def test_match_zoe_exact():
    res = match_participants("Zoe", [ZOE, ANTON])
    assert [r.user_id for r in res] == [ZOE.user_id]


def test_match_zoe_lowercase():
    res = match_participants("zoe", [ZOE, ANTON])
    assert [r.user_id for r in res] == [ZOE.user_id]


def test_match_anton_ru():
    res = match_participants("Антон", [ZOE, ANTON, NASTYA])
    assert [r.user_id for r in res] == [ANTON.user_id]


def test_match_anton_via_username():
    res = match_participants("anton", [ZOE, ANTON])
    assert [r.user_id for r in res] == [ANTON.user_id]


def test_match_missing_name_returns_empty():
    res = match_participants("Олег", [ZOE, ANTON])
    assert res == []


def test_match_ambiguous_two_zoes():
    res = match_participants("Зои", [ZOE, ZOEY_DUPLICATE])
    user_ids = {r.user_id for r in res}
    assert user_ids == {ZOE.user_id, ZOEY_DUPLICATE.user_id}


def test_match_substring_in_display_name():
    res = match_participants("ramirez", [ZOE, ANTON])
    assert [r.user_id for r in res] == [ZOE.user_id]


def test_match_empty_name_returns_empty():
    assert match_participants("", [ZOE]) == []
    assert match_participants("   ", [ZOE]) == []
