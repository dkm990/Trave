from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Заглушка для webhook режима. По умолчанию бот запускается в long polling.

    Для использования webhook см. README → запуск бота в режиме webhook (TODO).
    """
    payload = await request.json()
    return {"ok": True, "received": True, "update_id": payload.get("update_id")}
