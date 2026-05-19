from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        telegram_user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        user = (
            await self.session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
        ).scalar_one_or_none()
        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            self.session.add(user)
            await self.session.flush()
        else:
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                changed = True
            if changed:
                await self.session.flush()
        return user

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[User]:
        return (
            await self.session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
        ).scalar_one_or_none()
