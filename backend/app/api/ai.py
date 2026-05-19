from __future__ import annotations

from fastapi import APIRouter, Depends

from app.ai import get_ai_provider
from app.api.deps import current_user
from app.models.user import User
from app.schemas.common import AIIntentRequest, AIIntentResponse

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/parse-intent", response_model=AIIntentResponse)
async def parse_intent(
    payload: AIIntentRequest,
    user: User = Depends(current_user),
):
    provider = get_ai_provider()
    intent = await provider.parse_intent(
        payload.text,
        context={"trip_id": payload.trip_id, "user_id": user.id},
    )
    return AIIntentResponse(
        action=intent.action,
        confidence=intent.confidence,
        payload=intent.payload,
        needs_confirmation=intent.needs_confirmation,
        provider=provider.name,
    )
