from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseShare


# Все суммы для отображения нормализуем к этой точности.
DISPLAY_QUANT = Decimal("0.01")
ZERO_EPSILON = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(DISPLAY_QUANT, rounding=ROUND_HALF_UP)


@dataclass
class UserBalance:
    user_id: int
    paid: Decimal
    owes: Decimal
    net: Decimal  # paid - owes; positive => получает, negative => должен


@dataclass
class DebtTransfer:
    from_user_id: int
    to_user_id: int
    amount: Decimal


def calculate_balances_from_rows(
    expense_rows: Iterable[tuple[int, Decimal]],  # (payer_user_id, amount_base)
    share_rows: Iterable[tuple[int, Decimal]],   # (user_id, share_amount_base)
) -> List[UserBalance]:
    paid: dict[int, Decimal] = {}
    owes: dict[int, Decimal] = {}

    for payer_id, amount in expense_rows:
        paid[payer_id] = paid.get(payer_id, Decimal("0")) + Decimal(amount)

    for user_id, share in share_rows:
        owes[user_id] = owes.get(user_id, Decimal("0")) + Decimal(share)

    user_ids = set(paid) | set(owes)
    result: list[UserBalance] = []
    for uid in user_ids:
        p = _q(paid.get(uid, Decimal("0")))
        o = _q(owes.get(uid, Decimal("0")))
        net = p - o
        # Snap-to-zero: микрохвосты от конвертации/округления считаем за ноль.
        if abs(net) < ZERO_EPSILON:
            net = Decimal("0.00")
        result.append(UserBalance(user_id=uid, paid=p, owes=o, net=_q(net)))
    result.sort(key=lambda b: b.user_id)
    return result


def simplify_debts(balances: List[UserBalance]) -> List[DebtTransfer]:
    """Жадный алгоритм минимизации количества переводов.
    Округляем до сотых для устойчивости к плавающим хвостам.
    """
    eps = Decimal("0.01")
    creditors = sorted(
        [(b.user_id, b.net) for b in balances if b.net > eps],
        key=lambda x: -x[1],
    )
    debtors = sorted(
        [(b.user_id, -b.net) for b in balances if b.net < -eps],
        key=lambda x: -x[1],
    )

    transfers: list[DebtTransfer] = []
    i = j = 0
    creditors_m = [list(x) for x in creditors]
    debtors_m = [list(x) for x in debtors]

    while i < len(debtors_m) and j < len(creditors_m):
        debtor_id, debt = debtors_m[i]
        creditor_id, credit = creditors_m[j]
        amount = min(debt, credit)
        if amount > eps:
            transfers.append(
                DebtTransfer(
                    from_user_id=debtor_id,
                    to_user_id=creditor_id,
                    amount=amount.quantize(Decimal("0.01")),
                )
            )
        debtors_m[i][1] -= amount
        creditors_m[j][1] -= amount
        if debtors_m[i][1] <= eps:
            i += 1
        if creditors_m[j][1] <= eps:
            j += 1
    return transfers


class BalanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def calculate_balances(self, trip_id: int) -> List[UserBalance]:
        expenses = (
            await self.session.execute(
                select(Expense.payer_user_id, Expense.amount_base)
                .where(Expense.trip_id == trip_id, Expense.status == "confirmed")
            )
        ).all()
        shares = (
            await self.session.execute(
                select(ExpenseShare.user_id, ExpenseShare.share_amount_base)
                .join(Expense, Expense.id == ExpenseShare.expense_id)
                .where(Expense.trip_id == trip_id, Expense.status == "confirmed")
            )
        ).all()

        return calculate_balances_from_rows(
            [(r[0], r[1]) for r in expenses],
            [(r[0], r[1]) for r in shares],
        )

    async def simplified_debts(self, trip_id: int) -> List[DebtTransfer]:
        balances = await self.calculate_balances(trip_id)
        return simplify_debts(balances)
