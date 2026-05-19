"""Shared helpers for aviation providers."""

from __future__ import annotations

import re


def normalize_flight_number(value: str) -> str:
    """Normalize user-entered flight numbers to compact IATA form.

    Examples:
      "U6 783" -> "U6783"
      "u6-783" -> "U6783"
      " TK 1723 " -> "TK1723"
    """
    return re.sub(r"[^A-Z0-9]", "", value.strip().upper())
