from decimal import Decimal

from app.services.formatting import format_money


def test_format_money_thousands_separator():
    assert format_money(Decimal("1203.34"), "RUB") == "1\u00a0203.34 RUB"


def test_format_money_two_decimals_for_whole_number():
    assert format_money(Decimal("100"), "RUB") == "100.00 RUB"


def test_format_money_rounds_half_up():
    assert format_money(Decimal("1.005"), "USD") == "1.01 USD"


def test_format_money_negative():
    assert format_money(Decimal("-1234.5"), "RUB") == "-1\u00a0234.50 RUB"


def test_format_money_no_currency():
    assert format_money(Decimal("100.00")) == "100.00"


def test_format_money_large_vnd():
    assert format_money(Decimal("1200000"), "VND") == "1\u00a0200\u00a0000.00 VND"
