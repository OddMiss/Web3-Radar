from __future__ import annotations

import hashlib
import hmac
import re
import time
import urllib.parse
from decimal import Decimal
from typing import Any

from ..config import Settings
from ..http import HttpClient
from ..models import EarnOffer, ProviderResult, RateTier
from .common import decimal, fraction_to_percent, status_name


class BinanceProvider:
    name = "Binance"

    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings = settings
        self.http = http

    def fetch(self) -> ProviderResult:
        offers: list[EarnOffer] = []
        errors: list[str] = []
        for asset in self.settings.stablecoins:
            try:
                offers.extend(self._fetch_public_flexible(asset))
            except Exception as exc:  # keep other assets/exchanges alive
                errors.append(f"{asset} flexible: {exc}")
        if self.settings.binance_api_key and self.settings.binance_api_secret:
            try:
                offers.extend(self._fetch_locked())
            except Exception as exc:
                errors.append(f"locked: {exc}")
        else:
            errors.append("locked products skipped: BINANCE_API_KEY/SECRET not configured")
        return ProviderResult(self.name, tuple(offers), "; ".join(errors))

    def _fetch_public_flexible(self, asset: str) -> list[EarnOffer]:
        url = (
            f"{self.settings.binance_web_base}/bapi/earn/v1/friendly/"
            "finance-earn/simple/product/simpleEarnProducts"
        )
        payload = self.http.get_json(url, params={"asset": asset})
        if str(payload.get("code")) != "000000":
            raise RuntimeError(payload.get("message") or "unexpected Binance response")
        results: list[EarnOffer] = []
        for group in payload.get("data", {}).get("list", []):
            for item in group.get("productDetailList") or []:
                if str(item.get("productType", "")).upper() != "LENDING_FLEXIBLE":
                    continue
                base_apr = fraction_to_percent(item.get("marketApr"))
                tiers: list[RateTier] = []
                tier_items = item.get("apyTierOption") or []
                for tier in tier_items:
                    bonus_apr = fraction_to_percent(tier.get("ratio"))
                    tiers.append(
                        RateTier(
                            min_amount=decimal(tier.get("beginAmount")),
                            max_amount=self._optional_decimal(tier.get("endAmount")),
                            apr_percent=base_apr + bonus_apr,
                            is_bonus=bonus_apr > 0,
                            note=f"基础 {base_apr}% + Bonus {bonus_apr}%",
                        )
                    )
                if tiers and tiers[-1].max_amount is not None:
                    tiers.append(
                        RateTier(
                            min_amount=tiers[-1].max_amount,
                            max_amount=None,
                            apr_percent=base_apr,
                            note="超出 Bonus 上限的基础利率",
                        )
                    )
                advertised = fraction_to_percent(item.get("apy")) or base_apr
                results.append(
                    EarnOffer(
                        exchange=self.name,
                        asset=str(item.get("asset") or group.get("asset") or asset).upper(),
                        product_type="flexible",
                        product_name="Simple Earn Flexible",
                        apr_percent=advertised,
                        status=status_name(item.get("status"), bool(item.get("sellOut"))),
                        min_amount=self._optional_decimal(item.get("minPurchaseAmount")),
                        max_amount=self._optional_decimal(item.get("maxPurchaseAmountPerUser")),
                        is_bonus=any(t.is_bonus for t in tiers),
                        tiers=tuple(tiers),
                        source="Binance Earn website API",
                        product_id=str(item.get("productId", "")),
                    )
                )
        return results

    def _fetch_locked(self) -> list[EarnOffer]:
        payload = self._signed_get("/sapi/v1/simple-earn/locked/list", {"size": 100})
        rows = payload.get("rows") or payload.get("data") or []
        allowed = set(self.settings.stablecoins)
        results: list[EarnOffer] = []
        for row in rows:
            detail = row.get("detail") or row
            quota = row.get("quota") or {}
            asset = str(detail.get("asset") or row.get("asset") or "").upper()
            if asset not in allowed:
                continue
            apr = fraction_to_percent(
                detail.get("apr") or detail.get("annualPercentageRate") or row.get("apr")
            )
            extra_apr = fraction_to_percent(detail.get("extraRewardAPR") or detail.get("boostApr"))
            total_apr = apr + extra_apr
            eligibility = ""
            if extra_apr:
                eligibility = f"含额外奖励 {extra_apr}%"
            results.append(
                EarnOffer(
                    exchange=self.name,
                    asset=asset,
                    product_type="fixed",
                    product_name="Simple Earn Locked",
                    apr_percent=total_apr,
                    status=status_name(detail.get("status"), bool(detail.get("isSoldOut"))),
                    duration_days=decimal(detail.get("duration")) or None,
                    min_amount=self._optional_decimal(quota.get("minimum")),
                    max_amount=self._optional_decimal(quota.get("totalPersonalQuota")),
                    is_bonus=extra_apr > 0,
                    eligibility=eligibility,
                    source="Binance Simple Earn API",
                    product_id=str(row.get("projectId") or detail.get("projectId") or ""),
                )
            )
        return results

    def _signed_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        signed = dict(params)
        signed["timestamp"] = int(time.time() * 1000)
        signed["recvWindow"] = 10000
        query = urllib.parse.urlencode(signed)
        signature = hmac.new(
            self.settings.binance_api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return self.http.get_json(
            f"{self.settings.binance_api_base}{path}?{query}&signature={signature}",
            headers={"X-MBX-APIKEY": self.settings.binance_api_key},
        )

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        if value is None or value == "" or str(value) in {"-1", "0.00000000"}:
            return None
        return decimal(value)


def parse_binance_tier_label(label: str) -> tuple[Decimal, Decimal | None]:
    """Parse official Binance labels such as '0-1000USDT' defensively."""
    values = re.findall(r"[0-9]+(?:\.[0-9]+)?", label.replace(",", ""))
    if not values:
        return Decimal("0"), None
    if len(values) == 1:
        return Decimal(values[0]), None
    return Decimal(values[0]), Decimal(values[1])
