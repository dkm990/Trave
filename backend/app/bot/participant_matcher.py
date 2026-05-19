"""Сопоставление имён из intent с TripMember.

Стратегия (по убыванию приоритета):
1. Exact match display_name / first_name / last_name / username (case-insensitive).
2. Exact match по транслитерированной версии (ru→en, en→ru через словарь имён).
3. Substring match (подстрока в любом из полей).
4. Если ничего — пусто.

Возвращаем список кандидатов: 0, 1 или несколько. Caller решает:
- 1 — использует напрямую
- 0 / >1 — открывает picker
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# Distinctly russian-spelled forms of common english names.
NAME_ALIASES_RU_TO_EN = {
    "зо": "zoe",
    "зоя": "zoe",
    "зое": "zoe",
    "зои": "zoe",
    "ант": "ant",
    "антон": "anton",
    "наст": "nast",
    "настя": "nastya",
    "дын": "duc",
    "дык": "duc",
    "майк": "mike",
    "майкл": "michael",
    "ал": "al",
    "алекс": "alex",
    "александр": "aleksandr",
    "анна": "anna",
    "ан": "an",
    "иван": "ivan",
    "пётр": "petr",
    "петр": "petr",
    "юра": "yura",
    "юрий": "yuri",
}

NAME_ALIASES_EN_TO_RU = {
    "zoe": "зо",
    "zoey": "зо",
    "anton": "антон",
    "nastya": "настя",
    "anna": "анна",
    "alex": "алекс",
    "michael": "майкл",
    "mike": "майк",
    "ivan": "иван",
    "yuri": "юрий",
    "duc": "дык",
}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower().replace("\u00a0", " ")


def _candidates_for_name(needle: str) -> set[str]:
    """Все «варианты» иголки, по которым можно матчить."""
    n = _norm(needle)
    out: set[str] = {n} if n else set()
    if n in NAME_ALIASES_RU_TO_EN:
        out.add(NAME_ALIASES_RU_TO_EN[n])
    if n in NAME_ALIASES_EN_TO_RU:
        out.add(NAME_ALIASES_EN_TO_RU[n])
    for prefix in (n[:3], n[:4]):
        if prefix in NAME_ALIASES_RU_TO_EN:
            out.add(NAME_ALIASES_RU_TO_EN[prefix])
        if prefix in NAME_ALIASES_EN_TO_RU:
            out.add(NAME_ALIASES_EN_TO_RU[prefix])
    return {x for x in out if x}


@dataclass
class MemberView:
    user_id: int
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None

    def haystacks(self) -> list[str]:
        out: list[str] = []
        if self.display_name:
            out.append(_norm(self.display_name))
            for token in self.display_name.split():
                out.append(_norm(token))
        if self.first_name:
            out.append(_norm(self.first_name))
        if self.last_name:
            out.append(_norm(self.last_name))
        if self.username:
            out.append(_norm(self.username))
        return [h for h in out if h]


def member_view_from_db(member, user=None) -> MemberView:
    return MemberView(
        user_id=member.user_id,
        display_name=member.display_name,
        first_name=getattr(user, "first_name", None) if user else None,
        last_name=getattr(user, "last_name", None) if user else None,
        username=getattr(user, "username", None) if user else None,
    )


def match_participants(
    name: str, members: Iterable[MemberView]
) -> list[MemberView]:
    """Возвращает кандидатов в порядке предпочтения."""
    needle_set = _candidates_for_name(name)
    if not needle_set:
        return []

    members_list = list(members)

    # Tier 1: exact equality по любому haystack
    exact: list[MemberView] = []
    for m in members_list:
        if any(h in needle_set for h in m.haystacks()):
            exact.append(m)
    if exact:
        return _dedup(exact)

    # Tier 2: substring (needle ⊂ haystack или haystack ⊂ needle для длинных)
    substr: list[MemberView] = []
    for m in members_list:
        for h in m.haystacks():
            for needle in needle_set:
                if needle in h or (len(needle) >= 4 and h in needle):
                    substr.append(m)
                    break
            else:
                continue
            break
    if substr:
        return _dedup(substr)

    return []


def _dedup(members: list[MemberView]) -> list[MemberView]:
    seen: set[int] = set()
    out: list[MemberView] = []
    for m in members:
        if m.user_id in seen:
            continue
        seen.add(m.user_id)
        out.append(m)
    return out
