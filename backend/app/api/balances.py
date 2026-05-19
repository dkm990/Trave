from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.models.user import User
from app.schemas.common import BalanceOut, BalancesResponse, DebtOut
from app.services.balance_service import BalanceService, simplify_debts
from app.services.trip_service import TripService

router = APIRouter(prefix="/api/trips", tags=["balances"])


@router.get("/{trip_id}/balances", response_model=BalancesResponse)
async def get_balances(
    trip_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    trip_svc = TripService(session)
    trip = await trip_svc.get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    svc = BalanceService(session)
    balances = await svc.calculate_balances(trip_id)
    transfers = simplify_debts(balances)
    return BalancesResponse(
        base_currency=trip.default_currency,
        balances=[BalanceOut(user_id=b.user_id, paid=b.paid, owes=b.owes, net=b.net) for b in balances],
        transfers=[DebtOut(from_user_id=t.from_user_id, to_user_id=t.to_user_id, amount=t.amount) for t in transfers],
    )
