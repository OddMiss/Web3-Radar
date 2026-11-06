from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
        try:
            return ProviderResult(self.name, tuple(self._fetch_public_products()))
        except Exception as endpoint_error:
            try:
                html = self.http.get_text(f"{self.settings.bitget_web_base}/finance")
                offers = tuple(self._parse_webpage(html))
                return ProviderResult(
                    self.name,
                    offers,
                    f"public JSON endpoint failed; parsed webpage fallback: {endpoint_error}",
                )
            except Exception as webpage_error:
                public_error = f"endpoint: {endpoint_error}; webpage: {webpage_error}"
            if self._has_api_credentials():
                api_result = self._fetch_from_api()
                warning = f"public sources failed; used authenticated API fallback: {public_error}"
                return ProviderResult(api_result.exchange, api_result.offers, warning)
            return ProviderResult(
                self.name,
                (),
                f"Bitget public product sources failed: {public_error}",
            )

    def _fetch_public_products(self) -> list[EarnOffer]:
        payload = self.http.post_json(
            (
                f"{self.settings.bitget_web_base}/v1/finance/polymerization/"
                "product/entire/list/v3"
            ),
            data={
                "secondBizLineList": [],
                "guaranteed": True,
                "webReq": True,
                "languageType": 0,
            },
            headers={
                "Origin": self.settings.bitget_web_base,
                "Referer": f"{self.settings.bitget_web_base}/finance",
            },
        )
        if str(payload.get("code")) != "200" or not isinstance(payload.get("data"), list):
            raise RuntimeError(payload.get("msg") or "unexpected Bitget webpage API response")
        return self._parse_list_data(payload["data"])

    def _fetch_from_api(self) -> ProviderResult:
        offers: list[EarnOffer] = []
        errors: list[str] = []
        for asset in self.settings.stablecoins:
            try:
                offers.extend(self._fetch_asset(asset))
            except Exception as exc:
                errors.append(f"{asset}: {exc}")
        return ProviderResult(self.name, tuple(offers), "; ".join(errors))

    def _parse_webpage(self, html: str) -> list[EarnOffer]:
        marker = "window.__ZEUS_REACT_QUERY_STATE__ = "
        start = html.find(marker)
        if start < 0:
            raise RuntimeError("embedded product state not found")
        start += len(marker)
        end = html.find("</script>", start)
        if end < 0:
            raise RuntimeError("embedded product state is incomplete")
        raw_state = html[start:end].strip().removesuffix(";")
        state = json.loads(raw_state)
        page_data: dict[str, Any] | None = None
        for query in state.get("queries") or []:
            query_key = query.get("queryKey") or []
            if query_key and query_key[0] == "earning-overview-prefetch":
                page_data = (query.get("state") or {}).get("data")
                break
        if not page_data or not isinstance(page_data.get("listData"), list):
            raise RuntimeError("Bitget product listData not found")

        return self._parse_list_data(page_data["listData"])

    def _parse_list_data(self, list_data: list[dict[str, Any]]) -> list[EarnOffer]:
        allowed_assets = set(self.settings.stablecoins)
        offers: list[EarnOffer] = []
        seen: set[str] = set()
        for coin in list_data:
            asset = str(coin.get("coinName") or "").upper()
            if asset not in allowed_assets:
                continue
            for group in coin.get("bizLineProductList") or []:
                business_line = str(group.get("secondBizLine") or "")
                if business_line not in {"Savings", "CashPlus"}:
                    continue
                for item in group.get("productList") or []:
                    product_id = str(item.get("id") or item.get("productId") or "")
                    if not product_id or product_id in seen or item.get("visibleApy") is False:
                        continue
                    seen.add(product_id)
                    offers.append(self._parse_web_product(asset, business_line, group, item))
        return offers

    def _parse_web_product(
        self,
        asset: str,
        business_line: str,
        group: dict[str, Any],
        item: dict[str, Any],
    ) -> EarnOffer:
        tier_rows = item.get("apyList") or []
        high_first_tier = (
            len(tier_rows) > 1
            and percent_text(tier_rows[0].get("apy"))
            > percent_text(tier_rows[-1].get("apy"))
        )
        tiers = tuple(
            RateTier(
                min_amount=decimal(tier.get("minStepValue")),
                max_amount=self._optional_decimal(tier.get("maxStepValue")),
                apr_percent=percent_text(tier.get("apy")),
                is_bonus=index == 0 and high_first_tier,
                note="首档高息" if index == 0 and high_first_tier else "",
            )
            for index, tier in enumerate(tier_rows)
        )
        apr = max(
            (tier.apr_percent for tier in tiers),
            default=percent_text(item.get("maxApy") or item.get("apr")),
        )
        level = int(item.get("productLevel") or group.get("productLevel") or 1)
        product_type = "flexible" if int(item.get("periodType") or 1) == 1 else "fixed"
        if business_line == "CashPlus":
            product_name = "Cash Plus"
        elif level > 1:
            product_name = "VIP Simple Earn"
        else:
            product_name = "Simple Earn"
        return EarnOffer(
            exchange=self.name,
            asset=asset,
            product_type=product_type,
            product_name=product_name,
            apr_percent=apr,
            status=self._web_status(item.get("status")),
            duration_days=(
                duration_to_days(item.get("period")) if product_type == "fixed" else None
            ),
            is_bonus=high_first_tier,
            eligibility="VIP" if level > 1 else "",
            tiers=tiers,
            source="Bitget public Earn webpage",
            product_id=str(item.get("id") or item.get("productId") or ""),
        )

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

    def _has_api_credentials(self) -> bool:
        return all(
            (
                self.settings.bitget_api_key,
                self.settings.bitget_api_secret,
                self.settings.bitget_api_passphrase,
            )
        )

    @staticmethod
    def _web_status(value: Any) -> str:
        if str(value) == "2":
            return "available"
        if str(value) in {"3", "4", "6"}:
            return "sold_out"
        if str(value) == "1":
            return "not_started"
        return str(value or "unknown")

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        if value is None or value == "" or str(value) in {"-1", "0"}:
            return None
        return decimal(value)
