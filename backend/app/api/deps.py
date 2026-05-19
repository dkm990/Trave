from __future__ import annotations

from typing import AsyncIterator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.telegram_auth import (
    TelegramAuthError,
    TelegramInitData,
    parse_init_data,
    validate_init_data,
)
from app.config import get_settings
from app.database import get_session_factory
from app.models.user import User
from app.services.user_service import UserService


async def db_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def current_user(
    session: AsyncSession = Depends(db_session),
    x_telegram_init_data: Optional[str] = Header(default=None, alias="X-Telegram-Init-Data"),
    x_telegram_user_id: Optional[int] = Header(default=None, alias="X-Telegram-User-Id"),
) -> User:
    settings = get_settings()
    init: TelegramInitData | None = None

    if x_telegram_init_data:
        try:
            if settings.telegram_bot_token:
                init = validate_init_data(x_telegram_init_data, settings.telegram_bot_token)
            else:
                init = parse_init_data(x_telegram_init_data)
        except TelegramAuthError as exc:
            if not settings.dev_allow_insecure_auth:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
                ) from exc

    if init is None and settings.dev_allow_insecure_auth and x_telegram_user_id:
        # dev shortcut
        svc = UserService(session)
        return await svc.get_or_create(telegram_user_id=int(x_telegram_user_id))

    if init is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram init data missing",
        )

    svc = UserService(session)
    return await svc.get_or_create(
        telegram_user_id=init.user_id,
        username=init.username,
        first_name=init.first_name,
        last_name=init.last_name,
    )
