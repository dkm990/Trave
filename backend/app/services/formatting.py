"""Helpers для отображения денежных сумм пользователю."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def format_money(amount: Decimal | str | float | int, currency: str = "") -> str:
    """Форматирует сумму как '1 203.34 RUB'.

    - Всегда 2 знака после запятой.
    - Тысячи разделяет неразрывным пробелом (\\u00a0), чтобы Telegram не
      рвал число по концу строки.
    - Возможен отрицательный знак ('-1 200.00 RUB').
    """
    d = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    abs_d = abs(d)
    int_part, _, frac_part = f"{abs_d:.2f}".partition(".")
    grouped = ""
    for i, ch in enumerate(reversed(int_part)):
        if i and i % 3 == 0:
            grouped = "\u00a0" + grouped
        grouped = ch + grouped
    out = f"{sign}{grouped}.{frac_part}"
    if currency:
        return f"{out} {currency.upper()}"
    return out


def format_dual(
    original_amount,
    original_currency: str,
    base_amount,
    base_currency: str,
) -> str:
    """Возвращает 'X TRY ≈ Y RUB' или 'X RUB' (если валюты совпадают)."""
    o_cur = (original_currency or "").upper()
    b_cur = (base_currency or "").upper()
    original = format_money(original_amount, o_cur)
    if o_cur == b_cur:
        return original
    base = format_money(base_amount, b_cur)
    return f"{original} ≈ {base}"
