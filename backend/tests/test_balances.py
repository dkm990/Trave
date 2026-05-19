from decimal import Decimal

from app.services.balance_service import (
    UserBalance,
    calculate_balances_from_rows,
    simplify_debts,
)
from app.services.expense_service import split_equally


def test_split_equally_even():
    shares = split_equally(Decimal("300.00"), [1, 2, 3])
    assert shares == {1: Decimal("100.00"), 2: Decimal("100.00"), 3: Decimal("100.00")}


def test_split_equally_with_remainder():
    shares = split_equally(Decimal("100.00"), [1, 2, 3])
    # 33.33 * 3 = 99.99 → остаток 0.01 идёт первому
    assert sum(shares.values()) == Decimal("100.00")
    assert shares[1] == Decimal("33.34")
    assert shares[2] == Decimal("33.33")
    assert shares[3] == Decimal("33.33")


def test_calculate_balances_simple():
    expenses = [(1, Decimal("300.00"))]
    shares = [
        (1, Decimal("100.00")),
        (2, Decimal("100.00")),
        (3, Decimal("100.00")),
    ]
    balances = calculate_balances_from_rows(expenses, shares)
    by_user = {b.user_id: b for b in balances}
    assert by_user[1].net == Decimal("200.00")
    assert by_user[2].net == Decimal("-100.00")
    assert by_user[3].net == Decimal("-100.00")


def test_simplify_debts_two_creditors():
    balances = [
        UserBalance(1, Decimal("0"), Decimal("0"), Decimal("100")),
        UserBalance(2, Decimal("0"), Decimal("0"), Decimal("50")),
        UserBalance(3, Decimal("0"), Decimal("0"), Decimal("-150")),
    ]
    transfers = simplify_debts(balances)
    assert len(transfers) == 2
    total = sum(t.amount for t in transfers)
    assert total == Decimal("150.00")


def test_simplify_debts_minimal_count():
    balances = [
        UserBalance(1, Decimal("0"), Decimal("0"), Decimal("300")),
        UserBalance(2, Decimal("0"), Decimal("0"), Decimal("-100")),
        UserBalance(3, Decimal("0"), Decimal("0"), Decimal("-100")),
        UserBalance(4, Decimal("0"), Decimal("0"), Decimal("-100")),
    ]
    transfers = simplify_debts(balances)
    assert len(transfers) == 3
    assert all(t.to_user_id == 1 for t in transfers)


def test_simplify_debts_settled():
    balances = [
        UserBalance(1, Decimal("0"), Decimal("0"), Decimal("0")),
        UserBalance(2, Decimal("0"), Decimal("0"), Decimal("0")),
    ]
    assert simplify_debts(balances) == []


# Edge cases inspired by Spliit `getSuggestedReimbursements` reference review.

def test_simplify_debts_chained():
    """3 creditors / 1 big debtor: exactly 3 transfers, all from the debtor."""
    balances = [
        UserBalance(1, Decimal("0"), Decimal("0"), Decimal("100")),
        UserBalance(2, Decimal("0"), Decimal("0"), Decimal("100")),
        UserBalance(3, Decimal("0"), Decimal("0"), Decimal("100")),
        UserBalance(4, Decimal("0"), Decimal("0"), Decimal("-300")),
    ]
    transfers = simplify_debts(balances)
    assert len(transfers) == 3
    assert all(t.from_user_id == 4 for t in transfers)
    assert sum(t.amount for t in transfers) == Decimal("300.00")


def test_simplify_debts_zero_sum_invariant():
    """Sum of transfers equals |creditors| (or |debtors|); transfers go debtor -> creditor."""
    balances = [
        UserBalance(1, Decimal("0"), Decimal("0"), Decimal("75")),
        UserBalance(2, Decimal("0"), Decimal("0"), Decimal("25")),
        UserBalance(3, Decimal("0"), Decimal("0"), Decimal("-40")),
        UserBalance(4, Decimal("0"), Decimal("0"), Decimal("-60")),
    ]
    transfers = simplify_debts(balances)
    total = sum(t.amount for t in transfers)
    assert total == Decimal("100.00")
    for t in transfers:
        assert t.from_user_id in {3, 4}
        assert t.to_user_id in {1, 2}


def test_simplify_debts_ignores_below_epsilon():
    """Net amounts under 0.01 must be treated as settled (no spurious transfers)."""
    balances = [
        UserBalance(1, Decimal("0"), Decimal("0"), Decimal("0.005")),
        UserBalance(2, Decimal("0"), Decimal("0"), Decimal("-0.005")),
    ]
    assert simplify_debts(balances) == []


def test_split_equally_two_participants_odd_amount():
    """Sum of shares must equal the input amount with 0.01 precision.

    Our implementation gives the FIRST participant the rounding remainder
    (negative diff lands on participant 10): 49.99 + 50.00 = 99.99.
    """
    shares = split_equally(Decimal("99.99"), [10, 20])
    assert sum(shares.values()) == Decimal("99.99")
    assert shares[10] + shares[20] == Decimal("99.99")
    # 99.99 / 2 = 49.995 -> ROUND_HALF_UP -> 50.00; total 100.00; diff = -0.01.
    # diff is added to first participant => shares[10] = 49.99, shares[20] = 50.00.
    assert shares[10] == Decimal("49.99")
    assert shares[20] == Decimal("50.00")


def test_calculate_balances_empty():
    assert calculate_balances_from_rows([], []) == []


def test_calculate_balances_single_payer_full_share():
    """Payer pays for themselves only; net must be exactly zero."""
    expenses = [(1, Decimal("100.00"))]
    shares = [(1, Decimal("100.00"))]
    balances = calculate_balances_from_rows(expenses, shares)
    assert len(balances) == 1
    assert balances[0].user_id == 1
    assert balances[0].net == Decimal("0.00")


def test_single_payer_self_only_zero_net():
    """Один человек оплатил, делит сам с собой → итог 0.00 без хвоста."""
    expenses = [(1, Decimal("1203.34"))]
    shares = [(1, Decimal("1203.34"))]
    balances = calculate_balances_from_rows(expenses, shares)
    assert len(balances) == 1
    assert balances[0].net == Decimal("0.00")
    assert simplify_debts(balances) == []


def test_tiny_rounding_delta_snaps_to_zero():
    """net=-0.0016 (хвост от конвертации) должен схлопнуться в 0.00."""
    expenses = [(1, Decimal("1203.3384"))]
    shares = [(1, Decimal("1203.3400"))]
    balances = calculate_balances_from_rows(expenses, shares)
    assert balances[0].net == Decimal("0.00")
    assert simplify_debts(balances) == []


def test_multi_person_real_debts_not_lost():
    """Snap-to-zero не должен убивать настоящие долги."""
    expenses = [(1, Decimal("300.00"))]
    shares = [
        (1, Decimal("100.00")),
        (2, Decimal("100.00")),
        (3, Decimal("100.00")),
    ]
    balances = calculate_balances_from_rows(expenses, shares)
    transfers = simplify_debts(balances)
    assert len(transfers) == 2
    by_user = {b.user_id: b for b in balances}
    assert by_user[1].net == Decimal("200.00")
    assert by_user[2].net == Decimal("-100.00")


def test_balance_paid_owes_quantized_to_two_decimals():
    """paid и owes тоже отображаются с 2 знаками."""
    expenses = [(1, Decimal("99.999"))]
    shares = [(1, Decimal("99.999"))]
    balances = calculate_balances_from_rows(expenses, shares)
    assert balances[0].paid == Decimal("100.00")
    assert balances[0].owes == Decimal("100.00")
    assert balances[0].net == Decimal("0.00")
