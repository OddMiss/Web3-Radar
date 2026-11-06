from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from decimal import Decimal
from typing import Any

from ..config import Settings
from ..http import HttpClient
from ..models import EarnOffer, ProviderResult, RateTier
from .common import decimal, duration_to_days, percent_text, status_name


class BitgetProvider:
    name = "Bitget"
    path = "/api/v2/earn/savings/product"

    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings = settings
        self.http = http

    def fetch(self) -> ProviderResult:
        if not all(
            (
                self.settings.bitget_api_key,
                self.settings.bitget_api_secret,
                self.settings.bitget_api_passphrase,
            )
        ):
            return ProviderResult(
                self.name,
                (),
                "BITGET_API_KEY/SECRET/PASSPHRASE not configured; complete tier data requires a read-only key",
            )
        offers: list[EarnOffer] = []
        errors: list[str] = []
        for asset in self.settings.stablecoins:
            try:
                offers.extend(self._fetch_asset(asset))
            except Exception as exc:
                errors.append(f"{asset}: {exc}")
        return ProviderResult(self.name, tuple(offers), "; ".join(errors))

    def _fetch_asset(self, asset: str) -> list[EarnOffer]:
        params = {"coin": asset, "filter": "available_and_held"}
        payload = self._signed_get(params)
        if payload.get("code") != "00000":
            raise RuntimeError(payload.get("msg") or "unexpected Bitget response")
        results: list[EarnOffer] = []
        for item in payload.get("data") or []:
            tiers = tuple(
                RateTier(
                    min_amount=decimal(tier.get("minStepVal")),
                    max_amount=self._optional_decimal(tier.get("maxStepVal")),
                    apr_percent=percent_text(tier.get("currentApy")),
                    is_bonus=index == 0 and len(item.get("apyList") or []) > 1,
                    note="小额高息档" if index == 0 and len(item.get("apyList") or []) > 1 else "",
                )
                for index, tier in enumerate(item.get("apyList") or [])
            )
            highest = max((tier.apr_percent for tier in tiers), default=Decimal("0"))
            level = str(item.get("productLevel") or "normal")
            results.append(
                EarnOffer(
                    exchange=self.name,
                    asset=str(item.get("coin") or asset).upper(),
                    product_type="flexible" if item.get("periodType") == "flexible" else "fixed",
                    product_name="Savings",
                    apr_percent=highest,
                    status=status_name(item.get("status")),
                    duration_days=duration_to_days(item.get("period")),
                    min_amount=tiers[0].min_amount if tiers else None,
                    max_amount=tiers[-1].max_amount if tiers else None,
                    is_bonus=any(t.is_bonus for t in tiers),
                    eligibility="" if level == "normal" else level,
                    tiers=tiers,
                    source="Bitget Savings API",
                    product_id=str(item.get("productId", "")),
                )
            )
        return results

    def _signed_get(self, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        timestamp = str(int(time.time() * 1000))
        prehash = f"{timestamp}GET{self.path}?{query}"
        signature = base64.b64encode(
            hmac.new(
                self.settings.bitget_api_secret.encode(), prehash.encode(), hashlib.sha256
            ).digest()
        ).decode()
        headers = {
            "ACCESS-KEY": self.settings.bitget_api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-PASSPHRASE": self.settings.bitget_api_passphrase,
            "ACCESS-TIMESTAMP": timestamp,
            "locale": "en-US",
        }
        return self.http.get_json(
            f"{self.settings.bitget_api_base}{self.path}?{query}", headers=headers
        )

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        if value is None or value == "" or str(value) in {"-1", "0"}:
            return None
        return decimal(value)
