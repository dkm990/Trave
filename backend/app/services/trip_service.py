from __future__ import annotations

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.trip import Trip, TripMember
from app.models.user import User


class TripService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_trip(
        self,
        title: str,
        owner: User,
        default_currency: str = "RUB",
        telegram_chat_id: Optional[int] = None,
    ) -> Trip:
        trip = Trip(
            title=title.strip(),
            default_currency=default_currency.upper(),
            created_by_user_id=owner.id,
            telegram_chat_id=telegram_chat_id,
        )
        self.session.add(trip)
        await self.session.flush()

        member = TripMember(
            trip_id=trip.id,
            user_id=owner.id,
            display_name=owner.display_name,
            role="owner",
        )
        self.session.add(member)
        await self.session.flush()
        return trip

    async def list_user_trips(self, user_id: int) -> list[Trip]:
        stmt = (
            select(Trip)
            .join(TripMember, TripMember.trip_id == Trip.id)
            .where(TripMember.user_id == user_id, Trip.archived_at.is_(None))
            .options(selectinload(Trip.members))
            .order_by(Trip.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().unique())

    async def get_trip(self, trip_id: int) -> Optional[Trip]:
        stmt = select(Trip).where(Trip.id == trip_id).options(selectinload(Trip.members))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_trip_for_chat(self, chat_id: int) -> Optional[Trip]:
        stmt = (
            select(Trip)
            .where(Trip.telegram_chat_id == chat_id, Trip.archived_at.is_(None))
            .order_by(Trip.created_at.desc())
            .limit(1)
            .options(selectinload(Trip.members))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_trips_for_chat(self, chat_id: int) -> list[Trip]:
        stmt = (
            select(Trip)
            .where(Trip.telegram_chat_id == chat_id, Trip.archived_at.is_(None))
            .order_by(Trip.created_at.desc())
            .options(selectinload(Trip.members))
        )
        return list((await self.session.execute(stmt)).scalars().unique())

    async def add_member(self, trip: Trip, user: User) -> TripMember:
        existing = (
            await self.session.execute(
                select(TripMember).where(
                    TripMember.trip_id == trip.id, TripMember.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                await self.session.flush()
            return existing

        member = TripMember(
            trip_id=trip.id,
            user_id=user.id,
            display_name=user.display_name,
            role="member",
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def bind_to_chat(self, trip: Trip, chat_id: int) -> Trip:
        # One active trip per chat: detach other trips first.
        await self.session.execute(
            update(Trip)
            .where(Trip.telegram_chat_id == chat_id, Trip.id != trip.id)
            .values(telegram_chat_id=None)
        )
        trip.telegram_chat_id = chat_id
        await self.session.flush()
        return trip

    async def get_members(self, trip_id: int) -> list[TripMember]:
        stmt = select(TripMember).where(TripMember.trip_id == trip_id, TripMember.is_active.is_(True))
        return list((await self.session.execute(stmt)).scalars())

    async def get_members_with_users(self, trip_id: int) -> list[tuple[TripMember, User]]:
        """Возвращает пары (TripMember, User) для participant matching."""
        stmt = (
            select(TripMember, User)
            .join(User, User.id == TripMember.user_id)
            .where(TripMember.trip_id == trip_id, TripMember.is_active.is_(True))
        )
        return [(m, u) for m, u in (await self.session.execute(stmt)).all()]

    async def has_expenses(self, trip_id: int) -> bool:
        from app.models.expense import Expense

        row = (
            await self.session.execute(
                select(Expense.id).where(Expense.trip_id == trip_id).limit(1)
            )
        ).first()
        return row is not None

    async def set_default_currency(self, trip: Trip, currency: str) -> Trip:
        trip.default_currency = currency.upper()
        await self.session.flush()
        return trip

    async def set_local_currency(self, trip: Trip, currency: str) -> Trip:
        trip.local_currency = currency.upper()
        await self.session.flush()
        return trip

    async def rename(self, trip: Trip, new_title: str) -> Trip:
        trip.title = new_title.strip()[:200]
        await self.session.flush()
        return trip
