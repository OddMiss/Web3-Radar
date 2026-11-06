from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


def decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    text = str(value).strip().replace("%", "").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return default


def fraction_to_percent(value: Any) -> Decimal:
    return decimal(value) * Decimal("100")


def percent_text(value: Any) -> Decimal:
    return decimal(value)


def duration_to_days(value: Any) -> Decimal | None:
    if value is None or value == "" or str(value) == "0":
        return None
    text = str(value).strip().lower()
    match = re.fullmatch(r"([0-9.]+)\s*([dhm]?)", text)
    if not match:
        return decimal(value) or None
    number = decimal(match.group(1))
    unit = match.group(2)
    if unit == "h":
        return number / Decimal("24")
    if unit == "m":
        return number * Decimal("30")
    return number


def status_name(value: Any, sold_out: bool = False) -> str:
    if sold_out:
        return "sold_out"
    text = str(value or "").strip().lower()
    if text in {"available", "enable", "enabled", "in_progress", "1", "true"}:
        return "available"
    if text in {"soldout", "sold_out", "sold out", "2"}:
        return "sold_out"
    if text in {"notstarted", "not_started"}:
        return "not_started"
    return text or "available"
