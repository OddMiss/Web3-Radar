from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RateTier:
    min_amount: Decimal
    max_amount: Decimal | None
    apr_percent: Decimal
    is_bonus: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_amount": str(self.min_amount),
            "max_amount": None if self.max_amount is None else str(self.max_amount),
            "apr_percent": str(self.apr_percent),
            "is_bonus": self.is_bonus,
            "note": self.note,
        }


@dataclass(frozen=True)
class EarnOffer:
    exchange: str
    asset: str
    product_type: str
    product_name: str
    apr_percent: Decimal
    status: str = "available"
    duration_days: Decimal | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    is_bonus: bool = False
    eligibility: str = ""
    tiers: tuple[RateTier, ...] = field(default_factory=tuple)
    source: str = ""
    product_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("apr_percent", "duration_days", "min_amount", "max_amount"):
            value = result[key]
            result[key] = None if value is None else str(value)
        result["tiers"] = [tier.to_dict() for tier in self.tiers]
        return result


@dataclass(frozen=True)
class ProviderResult:
    exchange: str
    offers: tuple[EarnOffer, ...]
    error: str = ""
