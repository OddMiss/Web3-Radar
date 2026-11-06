from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..config import Settings
from ..http import HttpClient
from ..models import EarnOffer, ProviderResult, RateTier
from .common import decimal, duration_to_days, percent_text, status_name


class BybitProvider:
    name = "Bybit"

    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings = settings
        self.http = http

    def fetch(self) -> ProviderResult:
        offers: list[EarnOffer] = []
        errors: list[str] = []
        for asset in self.settings.stablecoins:
            try:
                offers.extend(self._fetch_flexible(asset))
            except Exception as exc:
                if not self._is_unsupported(exc):
                    errors.append(f"{asset} flexible: {exc}")
            try:
                offers.extend(self._fetch_fixed(asset))
            except Exception as exc:
                if not self._is_unsupported(exc):
                    errors.append(f"{asset} fixed: {exc}")
        return ProviderResult(self.name, tuple(offers), "; ".join(errors))

    def _fetch_flexible(self, asset: str) -> list[EarnOffer]:
        payload = self.http.get_json(
            f"{self.settings.bybit_api_base}/v5/earn/product",
            params={"category": "FlexibleSaving", "coin": asset},
        )
        self._check(payload)
        results: list[EarnOffer] = []
        for item in payload.get("result", {}).get("list", []):
            tier_rows = item.get("tierAprDetails") or []
            tiers = tuple(
                RateTier(
                    min_amount=decimal(tier.get("min")),
                    max_amount=self._optional_decimal(tier.get("max")),
                    apr_percent=percent_text(tier.get("estimateApr")),
                    is_bonus=index == 0 and len(tier_rows) > 1,
                    note="小额高息档" if index == 0 and len(tier_rows) > 1 else "",
                )
                for index, tier in enumerate(tier_rows)
            )
            bonus_events = item.get("bonusEvents") or []
            advertised_apr = max(
                (tier.apr_percent for tier in tiers),
                default=percent_text(item.get("estimateApr")),
            )
            eligibility = "; ".join(
                filter(
                    None,
                    (
                        f"额外奖励 {event.get('apr')} {event.get('coin', '')}".strip()
                        for event in bonus_events
                    ),
                )
            )
            results.append(
                EarnOffer(
                    exchange=self.name,
                    asset=str(item.get("coin") or asset).upper(),
                    product_type="flexible",
                    product_name="Flexible Saving",
                    apr_percent=advertised_apr,
                    status=status_name(item.get("status")),
                    min_amount=self._optional_decimal(item.get("minStakeAmount")),
                    max_amount=self._optional_decimal(item.get("maxStakeAmount")),
                    is_bonus=bool(bonus_events) or any(t.is_bonus for t in tiers),
                    eligibility=eligibility,
                    tiers=tiers,
                    source="Bybit Earn API",
                    product_id=str(item.get("productId", "")),
                )
            )
        return results

    def _fetch_fixed(self, asset: str) -> list[EarnOffer]:
        payload = self.http.get_json(
            f"{self.settings.bybit_api_base}/v5/earn/fixed-term/product",
            params={"coin": asset},
        )
        self._check(payload)
        results: list[EarnOffer] = []
        for item in payload.get("result", {}).get("list", []):
            tier_rows = item.get("tieredApyList") or []
            reward_rows = item.get("interestCoinApyList") or []
            tiers = tuple(
                RateTier(
                    min_amount=decimal(tier.get("min")),
                    max_amount=self._optional_decimal(tier.get("max")),
                    apr_percent=percent_text(tier.get("apy")),
                    is_bonus=index == 0 and len(tier_rows) > 1,
                )
                for index, tier in enumerate(tier_rows)
            )
            reward_apr = sum(
                (percent_text(reward.get("apy")) for reward in reward_rows), Decimal("0")
            )
            apr = max((tier.apr_percent for tier in tiers), default=reward_apr)
            restrictions: list[str] = []
            if item.get("specialUserGroupRequired"):
                restrictions.append(str(item.get("specialUserGroupInfo") or "限定用户"))
            if item.get("isVip"):
                restrictions.append("VIP")
            results.append(
                EarnOffer(
                    exchange=self.name,
                    asset=str(item.get("coin") or asset).upper(),
                    product_type="fixed",
                    product_name=str(item.get("category") or "Fixed Saving"),
                    apr_percent=apr,
                    status=status_name(item.get("status")),
                    duration_days=duration_to_days(item.get("duration")),
                    min_amount=self._optional_decimal(item.get("minStakeAmount")),
                    max_amount=self._optional_decimal(item.get("maxStakeAmount")),
                    is_bonus=bool(restrictions) or any(t.is_bonus for t in tiers),
                    eligibility=" / ".join(restrictions),
                    tiers=tiers,
                    source="Bybit Fixed Saving API",
                    product_id=str(item.get("productId", "")),
                )
            )
        return results

    @staticmethod
    def _check(payload: dict[str, Any]) -> None:
        if payload.get("retCode") != 0:
            raise RuntimeError(payload.get("retMsg") or "unexpected Bybit response")

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        if value is None or value == "" or str(value) in {"-1", "0"}:
            return None
        return decimal(value)

    @staticmethod
    def _is_unsupported(error: Exception) -> bool:
        text = str(error).lower()
        return "invalid coin" in text or "invalid parameter: invalid coin" in text
