from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.models.user import User
from app.schemas.common import (
    ExpenseCreateRequest,
    ExpenseOut,
    ExpenseUpdateRequest,
    TripCreateRequest,
    TripOut,
    TripUpdateRequest,
)
from app.services.balance_service import BalanceService, simplify_debts
from app.services.currency_service import CurrencyService
from app.services.expense_service import (
    ExpenseEditInput,
    ExpenseFilters,
    ExpenseInput,
    ExpenseService,
)
from app.services.trip_service import TripService

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("", response_model=list[TripOut])
async def list_trips(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    return await TripService(session).list_user_trips(user.id)


@router.post("", response_model=TripOut)
async def create_trip(
    payload: TripCreateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    trip = await TripService(session).create_trip(
        title=payload.title, owner=user, default_currency=payload.default_currency,
    )
    await session.refresh(trip, ["members"])
    return trip


@router.get("/{trip_id}", response_model=TripOut)
async def get_trip(
    trip_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    trip = await TripService(session).get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    return trip


@router.patch("/{trip_id}", response_model=TripOut)
async def update_trip(
    trip_id: int,
    payload: TripUpdateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    svc = TripService(session)
    trip = await svc.get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    if payload.title is not None and payload.title.strip():
        await svc.rename(trip, payload.title)
    if payload.local_currency is not None:
        await svc.set_local_currency(trip, payload.local_currency)
    await session.refresh(trip, ["members"])
    return trip


@router.get("/{trip_id}/expenses", response_model=list[ExpenseOut])
async def list_expenses(
    trip_id: int,
    participant_id: Optional[int] = None,
    payer_id: Optional[int] = None,
    category: Optional[str] = None,
    currency: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    only_mine: bool = False,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    if not await TripService(session).get_trip(trip_id):
        raise HTTPException(404, "Trip not found")
    svc = ExpenseService(session, CurrencyService(session))
    rows = await svc.list_filtered(
        trip_id,
        ExpenseFilters(
            participant_id=participant_id,
            payer_id=payer_id,
            category=category,
            currency=currency,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount,
            search=search,
            status=status,
            only_mine=only_mine,
            viewer_user_id=user.id,
        ),
    )
    return rows


@router.post("/{trip_id}/expenses", response_model=ExpenseOut)
async def add_expense(
    trip_id: int,
    payload: ExpenseCreateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    svc = ExpenseService(session, CurrencyService(session))
    try:
        expense = await svc.add_expense(
            ExpenseInput(
                trip_id=trip_id,
                payer_user_id=payload.payer_user_id,
                title=payload.title,
                amount=payload.amount,
                currency=payload.currency,
                participant_user_ids=payload.participant_user_ids,
                category=payload.category,
                created_by_user_id=user.id,
                status="confirmed",
                note=payload.note,
                source="web",
                split_mode=payload.split_mode,
                custom_shares=payload.custom_shares,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    await session.refresh(expense, ["shares"])
    return expense


@router.get("/{trip_id}/expenses/{expense_id}", response_model=ExpenseOut)
async def get_expense(
    trip_id: int,
    expense_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    svc = ExpenseService(session, CurrencyService(session))
    expense = await svc.get_expense(expense_id)
    if not expense or expense.trip_id != trip_id:
        raise HTTPException(404, "Expense not found")
    return expense


@router.patch("/{trip_id}/expenses/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    trip_id: int,
    expense_id: int,
    payload: ExpenseUpdateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    svc = ExpenseService(session, CurrencyService(session))
    expense = await svc.get_expense(expense_id)
    if not expense or expense.trip_id != trip_id:
        raise HTTPException(404, "Expense not found")
    try:
        edited = await svc.edit_expense(
            expense_id,
            ExpenseEditInput(
                title=payload.title,
                amount=payload.amount,
                currency=payload.currency,
                category=payload.category,
                payer_user_id=payload.payer_user_id,
                participant_user_ids=payload.participant_user_ids,
                note=payload.note,
                split_mode=payload.split_mode,
                custom_shares=payload.custom_shares,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return edited


@router.post("/{trip_id}/expenses/{expense_id}/cancel", response_model=ExpenseOut)
async def cancel_expense(
    trip_id: int,
    expense_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    svc = ExpenseService(session, CurrencyService(session))
    expense = await svc.get_expense(expense_id)
    if not expense or expense.trip_id != trip_id:
        raise HTTPException(404, "Expense not found")
    canceled = await svc.cancel_expense(expense_id)
    await session.refresh(canceled, ["shares"])
    return canceled


@router.get("/{trip_id}/dashboard")
async def get_dashboard(
    trip_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    svc = TripService(session)
    trip = await svc.get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    members = await svc.get_members(trip_id)
    expense_svc = ExpenseService(session, CurrencyService(session))
    today = await expense_svc.today_summary(trip_id)
    analytics_trip = await expense_svc.analytics(trip_id, period="trip")
    balances = await BalanceService(session).calculate_balances(trip_id)
    transfers = simplify_debts(balances)
    name_by_id = {m.user_id: (m.display_name or f"user_{m.user_id}") for m in members}

    return {
        "trip": {
            "id": trip.id,
            "title": trip.title,
            "default_currency": trip.default_currency,
            "local_currency": trip.local_currency,
            "members": [
                {"user_id": m.user_id, "display_name": name_by_id[m.user_id], "role": m.role}
                for m in members
            ],
        },
        "today": {
            "total": str(today.total),
            "base_currency": today.base_currency or trip.default_currency,
            "by_original_currency": {k: str(v) for k, v in today.by_original_currency.items()},
            "by_category": {k: str(v) for k, v in today.by_category.items()},
            "count": today.count,
        },
        "trip_total": {
            "total_display": str(analytics_trip.total_display),
            "display_currency": analytics_trip.display_currency or trip.default_currency,
            "totals_by_original_currency": {
                k: str(v) for k, v in analytics_trip.totals_by_original_currency.items()
            },
            "by_category": {k: str(v) for k, v in analytics_trip.by_category_display.items()},
            "count": analytics_trip.count,
        },
        "balances": [
            {
                "user_id": b.user_id,
                "name": name_by_id.get(b.user_id, str(b.user_id)),
                "paid": str(b.paid),
                "owes": str(b.owes),
                "net": str(b.net),
            }
            for b in balances
        ],
        "transfers": [
            {
                "from_user_id": t.from_user_id,
                "to_user_id": t.to_user_id,
                "from_name": name_by_id.get(t.from_user_id, str(t.from_user_id)),
                "to_name": name_by_id.get(t.to_user_id, str(t.to_user_id)),
                "amount": str(t.amount),
            }
            for t in transfers
        ],
    }


@router.get("/{trip_id}/analytics")
async def get_analytics(
    trip_id: int,
    period: str = Query(default="trip", pattern="^(trip|today)$"),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    svc = TripService(session)
    trip = await svc.get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    members = await svc.get_members(trip_id)
    name_by_id = {m.user_id: (m.display_name or f"user_{m.user_id}") for m in members}

    expense_svc = ExpenseService(session, CurrencyService(session))
    a = await expense_svc.analytics(trip_id, period=period)
    balance_svc = BalanceService(session)
    balances = await balance_svc.calculate_balances(trip_id)
    transfers = simplify_debts(balances)

    return {
        "trip": {
            "id": trip.id,
            "title": trip.title,
            "default_currency": trip.default_currency,
            "local_currency": trip.local_currency,
        },
        "period": a.period,
        "display_currency": a.display_currency or trip.default_currency,
        "local_currency": trip.local_currency,
        "total_display": str(a.total_display),
        "totals_by_original_currency": [
            {"currency": k, "amount": str(v)}
            for k, v in sorted(a.totals_by_original_currency.items(), key=lambda x: -x[1])
        ],
        "by_category": [
            {
                "category": cat,
                "amount_display": str(amt),
                "original": [
                    {"currency": ocur, "amount": str(oamt)}
                    for ocur, oamt in sorted(
                        (a.by_category_original.get(cat) or {}).items(),
                        key=lambda x: -x[1],
                    )
                ],
            }
            for cat, amt in a.by_category_display.items()
        ],
        "by_payer": [
            {
                "user_id": uid,
                "name": name_by_id.get(uid, str(uid)),
                "amount_display": str(amt),
            }
            for uid, amt in sorted(a.by_payer.items(), key=lambda x: -x[1])
        ],
        "by_participant": [
            {
                "user_id": uid,
                "name": name_by_id.get(uid, str(uid)),
                "share_display": str(amt),
            }
            for uid, amt in sorted(a.by_participant.items(), key=lambda x: -x[1])
        ],
        "by_day": [
            {"date": k, "amount_display": str(v)} for k, v in a.by_day.items()
        ],
        "debts": [
            {
                "from_user_id": t.from_user_id,
                "to_user_id": t.to_user_id,
                "from_name": name_by_id.get(t.from_user_id, str(t.from_user_id)),
                "to_name": name_by_id.get(t.to_user_id, str(t.to_user_id)),
                "amount": str(t.amount),
            }
            for t in transfers
        ],
        "count": a.count,
    }
