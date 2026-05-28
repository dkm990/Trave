"""Expense service: add, list, edit, cancel, analytics, today summary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_engine
from app.models.expense import Expense, ExpenseShare
from app.models.trip import Trip
from app.services.currency_service import CurrencyService


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


@dataclass
class ExpenseInput:
    trip_id: int
    payer_user_id: int
    title: str
    amount: Decimal
    currency: Optional[str] = None
    participant_user_ids: list[int] = None  # type: ignore[assignment]
    category: Optional[str] = None
    created_by_user_id: Optional[int] = None
    status: str = "confirmed"
    note: Optional[str] = None
    source: Optional[str] = None
    split_mode: str = "equal"
    custom_shares: Optional[dict[int, Decimal]] = None


@dataclass
class ExpenseEditInput:
    title: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    payer_user_id: Optional[int] = None
    participant_user_ids: Optional[list[int]] = None
    note: Optional[str] = None
    split_mode: Optional[str] = None
    custom_shares: Optional[dict[int, Decimal]] = None


@dataclass
class ExpenseFilters:
    participant_id: Optional[int] = None
    payer_id: Optional[int] = None
    category: Optional[str] = None
    currency: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    search: Optional[str] = None
    status: Optional[str] = None
    only_mine: bool = False
    viewer_user_id: Optional[int] = None


@dataclass
class TodaySummary:
    total: Decimal
    base_currency: Optional[str]
    by_original_currency: dict[str, Decimal]
    by_category: dict[str, Decimal]
    by_category_original: dict[str, dict[str, Decimal]]
    count: int


@dataclass
class AnalyticsResult:
    period: str
    total_display: Decimal
    display_currency: Optional[str]
    totals_by_original_currency: dict[str, Decimal]
    by_category_display: dict[str, Decimal]
    by_category_original: dict[str, dict[str, Decimal]]
    by_payer: dict[int, Decimal]
    by_participant: dict[int, Decimal]
    by_day: dict[str, Decimal]
    count: int


def compute_shares(
    total: Decimal,
    participant_user_ids: list[int],
    mode: str = "equal",
    custom_shares: Optional[dict[int, Decimal]] = None,
) -> dict[int, Decimal]:
    """Compute share_amount_base for each participant."""
    if not participant_user_ids:
        raise ValueError("participants required")

    if mode == "by_amount" and custom_shares:
        shares: dict[int, Decimal] = {}
        for uid, share_amt in custom_shares.items():
            if uid in participant_user_ids:
                shares[uid] = _q2(share_amt)
        remaining = set(participant_user_ids) - set(shares.keys())
        if remaining:
            assigned = sum(shares.values(), Decimal("0"))
            leftover = total - assigned
            if leftover > 0 and len(remaining) > 0:
                per_person = _q2(leftover / len(remaining))
                for uid in remaining:
                    shares[uid] = per_person
        return shares

    if mode == "by_percent" and custom_shares:
        shares = {}
        for uid, pct in custom_shares.items():
            if uid in participant_user_ids:
                share = _q2(total * pct / Decimal("100"))
                shares[uid] = share
        remaining = set(participant_user_ids) - set(shares.keys())
        if remaining:
            assigned = sum(shares.values(), Decimal("0"))
            leftover = total - assigned
            if leftover > 0 and len(remaining) > 0:
                per_person = _q2(leftover / len(remaining))
                for uid in remaining:
                    shares[uid] = per_person
        return shares

    # Equal split
    per_person = _q2(total / len(participant_user_ids))
    adjustment = total - per_person * len(participant_user_ids)
    shares = {uid: per_person for uid in participant_user_ids}
    if adjustment != 0:
        shares[participant_user_ids[0]] += adjustment
    return shares


def split_equally(total: Decimal, participant_user_ids: list[int]) -> dict[int, Decimal]:
    """Backward-compatible wrapper for legacy imports/tests."""
    return compute_shares(total, participant_user_ids, mode="equal")


class ExpenseService:
    def __init__(self, session: AsyncSession, currency_service: CurrencyService) -> None:
        self.session = session
        self.currency = currency_service

    async def add_expense(self, payload: ExpenseInput) -> Expense:
        trip = (
            await self.session.execute(select(Trip).where(Trip.id == payload.trip_id))
        ).scalar_one()

        effective_currency = (payload.currency or trip.default_currency).upper()
        if not effective_currency:
            raise ValueError(f"Trip {trip.id} has no default_currency and no currency was provided")

        raw_base, rate_info = await self.currency.convert(
            payload.amount, effective_currency, trip.default_currency
        )

        expense = Expense(
            trip_id=payload.trip_id,
            payer_user_id=payload.payer_user_id,
            title=payload.title.strip()[:200],
            category=payload.category or None,
            amount_original=payload.amount,
            currency_original=effective_currency,
            amount_base=_q2(raw_base),
            base_currency=trip.default_currency,
            exchange_rate=rate_info.rate,
            exchange_rate_date=rate_info.rate_date,
            created_by_user_id=payload.created_by_user_id or payload.payer_user_id,
            status=payload.status,
            note=payload.note or None,
            source=payload.source or "web",
        )

        self.session.add(expense)
        await self.session.flush()

        # Compute participant shares
        participants = payload.participant_user_ids
        if not participants:
            participants = [payload.payer_user_id]

        custom_shares_base = None
        mode = payload.split_mode or "equal"
        if mode == "by_amount" and payload.custom_shares:
            custom_shares_base = {}
            for uid, share_orig in payload.custom_shares.items():
                converted, _ = await self.currency.convert(
                    share_orig, effective_currency, trip.default_currency
                )
                custom_shares_base[uid] = _q2(converted)
        elif mode == "by_percent" and payload.custom_shares:
            custom_shares_base = payload.custom_shares

        shares = compute_shares(
            Decimal(expense.amount_base), participants, mode, custom_shares_base
        )
        for uid, share in shares.items():
            self.session.add(
                ExpenseShare(
                    expense_id=expense.id, user_id=uid, share_amount_base=share
                )
            )
        await self.session.flush()
        await self.session.refresh(expense, ["shares"])
        return expense

    async def get_expense(self, expense_id: int) -> Optional[Expense]:
        stmt = (
            select(Expense)
            .where(Expense.id == expense_id)
            .options(selectinload(Expense.shares))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def edit_expense(self, expense_id: int, edit: ExpenseEditInput) -> Expense:
        """Редактирует расход. amount/currency → пересчёт base. participants → пересчёт shares."""
        expense = await self.get_expense(expense_id)
        if expense is None:
            raise ValueError(f"expense {expense_id} not found")

        if edit.title is not None:
            expense.title = edit.title.strip()[:200]
        if edit.category is not None:
            expense.category = edit.category or None
        if edit.payer_user_id is not None:
            expense.payer_user_id = edit.payer_user_id
        if edit.note is not None:
            expense.note = edit.note or None

        recalc_base = False
        new_amount = edit.amount if edit.amount is not None else expense.amount_original
        new_currency = (
            (edit.currency or expense.currency_original).upper()
            if edit.currency or edit.amount is not None
            else expense.currency_original
        )
        if edit.amount is not None or (
            edit.currency is not None and edit.currency.upper() != expense.currency_original
        ):
            recalc_base = True

        if recalc_base:
            trip = (
                await self.session.execute(select(Trip).where(Trip.id == expense.trip_id))
            ).scalar_one()
            raw_base, rate_info = await self.currency.convert(
                new_amount, new_currency, trip.default_currency
            )
            expense.amount_original = new_amount
            expense.currency_original = new_currency
            expense.amount_base = _q2(raw_base)
            expense.exchange_rate = rate_info.rate

        new_participants = edit.participant_user_ids
        if recalc_base or new_participants is not None or edit.split_mode is not None or edit.custom_shares is not None:
            participants = (
                new_participants
                if new_participants is not None
                else [s.user_id for s in expense.shares]
            )
            if not participants:
                raise ValueError("participants required")

            # ⚠️ CRITICAL: capture values BEFORE flush.
            # flush() expires object attributes — accessing them afterwards
            # triggers lazy-load in async session → greenlet_spawn error.
            _amount_base = expense.amount_base
            _currency_original = expense.currency_original
            _base_currency = expense.base_currency

            for s in list(expense.shares):
                await self.session.delete(s)
            await self.session.flush()

            mode = edit.split_mode or "equal"
            custom_shares_base = None
            if mode == "by_amount" and edit.custom_shares:
                custom_shares_base = {}
                new_cur = edit.currency if edit.currency else _currency_original
                for uid, share_orig in edit.custom_shares.items():
                    converted_share, _ = await self.currency.convert(
                        share_orig, new_cur, _base_currency
                    )
                    custom_shares_base[uid] = _q2(converted_share)
            elif mode == "by_percent" and edit.custom_shares:
                custom_shares_base = edit.custom_shares

            shares = compute_shares(
                Decimal(_amount_base), participants, mode, custom_shares_base,
            )
            for uid, share in shares.items():
                self.session.add(
                    ExpenseShare(
                        expense_id=expense.id, user_id=uid, share_amount_base=share
                    )
                )

        expense.updated_at = datetime.utcnow()
        expense.edited_count = (expense.edited_count or 0) + 1
        await self.session.flush()
        await self.session.refresh(expense, ["shares"])
        return expense

    async def cancel_expense(self, expense_id: int) -> Expense:
        expense = await self.get_expense(expense_id)
        if expense is None:
            raise ValueError(f"expense {expense_id} not found")
        expense.status = "canceled"
        expense.canceled_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(expense, ["shares"])
        return expense

    async def list_filtered(
        self, trip_id: int, filters: ExpenseFilters
    ) -> list[Expense]:
        stmt = (
            select(Expense)
            .where(Expense.trip_id == trip_id)
            .options(selectinload(Expense.shares))
        )

        if filters.participant_id:
            stmt = stmt.where(
                Expense.shares.any(ExpenseShare.user_id == filters.participant_id)
            )
        if filters.payer_id:
            stmt = stmt.where(Expense.payer_user_id == filters.payer_id)
        if filters.category:
            stmt = stmt.where(Expense.category == filters.category)
        if filters.currency:
            stmt = stmt.where(Expense.currency_original == filters.currency.upper())
        if filters.date_from:
            stmt = stmt.where(Expense.created_at >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(Expense.created_at <= filters.date_to)
        if filters.min_amount is not None:
            stmt = stmt.where(Expense.amount_base >= filters.min_amount)
        if filters.max_amount is not None:
            stmt = stmt.where(Expense.amount_base <= filters.max_amount)
        if filters.search:
            like = f"%{filters.search.lower()}%"
            stmt = stmt.where(Expense.title.ilike(like))
        if filters.status:
            stmt = stmt.where(Expense.status == filters.status)

        stmt = stmt.order_by(Expense.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def today_summary(self, trip_id: int) -> TodaySummary:
        """Aggregate expenses for today (app timezone)."""
        from app.config import get_settings

        settings = get_settings()
        tz_name = settings.app_timezone or "UTC"

        # Use SQLite datetime functions — simplest approach
        today_str = date.today().isoformat()
        stmt = (
            select(Expense)
            .where(
                Expense.trip_id == trip_id,
                Expense.status == "confirmed",
                func.date(Expense.created_at) == today_str,
            )
            .options(selectinload(Expense.shares))
        )
        expenses = list((await self.session.execute(stmt)).scalars())
        return self._build_summary(expenses)

    async def analytics(self, trip_id: int, *, period: str = "trip") -> AnalyticsResult:
        """Aggregate expenses per trip or today."""
        stmt = (
            select(Expense)
            .where(Expense.trip_id == trip_id, Expense.status != "canceled")
            .options(selectinload(Expense.shares))
        )
        if period == "today":
            stmt = stmt.where(func.date(Expense.created_at) == date.today().isoformat())

        stmt = stmt.order_by(Expense.created_at.desc())
        expenses = list((await self.session.execute(stmt)).scalars())

        # Determine display currency from trip
        trip = (
            await self.session.execute(select(Trip).where(Trip.id == trip_id))
        ).scalar_one_or_none()
        display_currency = trip.default_currency if trip else None

        total_display = Decimal("0")
        totals_by_orig: dict[str, Decimal] = {}
        by_category_display: dict[str, Decimal] = {}
        by_category_orig: dict[str, dict[str, Decimal]] = {}
        by_payer: dict[int, Decimal] = {}
        by_participant: dict[int, Decimal] = {}
        by_day: dict[str, Decimal] = {}

        for exp in expenses:
            amt = Decimal(exp.amount_base)
            cur = exp.currency_original
            total_display += amt
            totals_by_orig[cur] = totals_by_orig.get(cur, Decimal("0")) + exp.amount_original

            cat = exp.category or "other"
            by_category_display[cat] = by_category_display.get(cat, Decimal("0")) + amt
            by_category_orig.setdefault(cat, {})
            by_category_orig[cat][cur] = (
                by_category_orig[cat].get(cur, Decimal("0")) + exp.amount_original
            )

            by_payer[exp.payer_user_id] = (
                by_payer.get(exp.payer_user_id, Decimal("0")) + amt
            )

            for share in exp.shares:
                by_participant[share.user_id] = (
                    by_participant.get(share.user_id, Decimal("0"))
                    + share.share_amount_base
                )

            day_str = exp.created_at.strftime("%Y-%m-%d") if exp.created_at else "unknown"
            by_day[day_str] = by_day.get(day_str, Decimal("0")) + amt

        return AnalyticsResult(
            period=period,
            total_display=_q2(total_display),
            display_currency=display_currency,
            totals_by_original_currency=totals_by_orig,
            by_category_display=by_category_display,
            by_category_original=by_category_orig,
            by_payer=by_payer,
            by_participant=by_participant,
            by_day=dict(sorted(by_day.items(), reverse=True)),
            count=len(expenses),
        )

    def _build_summary(self, expenses: list[Expense]) -> TodaySummary:
        total = Decimal("0")
        by_orig: dict[str, Decimal] = {}
        by_cat: dict[str, Decimal] = {}
        by_cat_orig: dict[str, dict[str, Decimal]] = {}
        base_cur: Optional[str] = None

        for exp in expenses:
            total += Decimal(exp.amount_base)
            cur = exp.currency_original
            base_cur = exp.base_currency or base_cur
            by_orig[cur] = by_orig.get(cur, Decimal("0")) + exp.amount_original

            cat = exp.category or "other"
            by_cat[cat] = by_cat.get(cat, Decimal("0")) + Decimal(exp.amount_base)
            by_cat_orig.setdefault(cat, {})
            by_cat_orig[cat][cur] = (
                by_cat_orig[cat].get(cur, Decimal("0")) + exp.amount_original
            )

        return TodaySummary(
            total=_q2(total),
            base_currency=base_cur,
            by_original_currency=by_orig,
            by_category=dict(
                sorted(
                    by_cat.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
            by_category_original=by_cat_orig,
            count=len(expenses),
        )
