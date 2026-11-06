from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..config import Settings
from ..http import HttpClient
from ..models import EarnOffer, ProviderResult
from .common import decimal, duration_to_days, status_name


class OkxProvider:
    name = "OKX"

    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings = settings
        self.http = http

    def fetch(self) -> ProviderResult:
        offers: list[EarnOffer] = []
        errors: list[str] = []
        for asset in self.settings.stablecoins:
            try:
                offers.extend(self._fetch_market_rate(asset))
            except Exception as exc:
                if not self._is_unsupported(exc):
                    errors.append(f"{asset} market rate: {exc}")
        try:
            offers.extend(self._fetch_promotions())
        except Exception as exc:
            errors.append(f"website products: {exc}")
        return ProviderResult(self.name, tuple(self._deduplicate(offers)), "; ".join(errors))

    def _fetch_market_rate(self, asset: str) -> list[EarnOffer]:
        payload = self.http.get_json(
            f"{self.settings.okx_api_base}/api/v5/finance/savings/lending-rate-summary",
            params={"ccy": asset},
        )
        if payload.get("code") != "0":
            raise RuntimeError(payload.get("msg") or "unexpected OKX response")
        results: list[EarnOffer] = []
        for item in payload.get("data") or []:
            apr = decimal(item.get("estRate") or item.get("preRate")) * Decimal("100")
            results.append(
                EarnOffer(
                    exchange=self.name,
                    asset=str(item.get("ccy") or asset).upper(),
                    product_type="flexible",
                    product_name="Simple Earn Flexible (market estimate)",
                    apr_percent=apr,
                    source="OKX public Savings API",
                    product_id=f"market-{asset}",
                )
            )
        return results

    def _fetch_promotions(self) -> list[EarnOffer]:
        payload = self.http.get_json(
            f"{self.settings.okx_api_base}/priapi/v1/earn/simple-earn/all-products",
            params={"type": "all"},
        )
        if payload.get("code") not in (0, "0"):
            raise RuntimeError(payload.get("msg") or "unexpected OKX website response")
        data = payload.get("data") or {}
        container = data.get("allProducts") or data.get("all") or {}
        currencies = container.get("currencies") if isinstance(container, dict) else container
        allowed = set(self.settings.stablecoins)
        results: list[EarnOffer] = []
        for currency in currencies or []:
            asset = str((currency.get("investCurrency") or {}).get("currencyName") or "").upper()
            if asset not in allowed:
                continue
            for index, item in enumerate(currency.get("products") or []):
                values = ((item.get("rate") or {}).get("rateNum") or {}).get("value") or []
                if not values:
                    continue
                apr = max((decimal(value) for value in values), default=Decimal("0"))
                description = str(item.get("bonusDescription") or "").strip()
                product_type = self._product_type(item)
                is_bonus = bool(description) or 3 in (item.get("labels") or [])
                results.append(
                    EarnOffer(
                        exchange=self.name,
                        asset=asset,
                        product_type=product_type,
                        product_name="Simple Earn Promotion" if is_bonus else "Simple Earn",
                        apr_percent=apr,
                        status=status_name(item.get("purchaseStatus")),
                        duration_days=(
                            duration_to_days((item.get("term") or {}).get("value"))
                            if product_type == "fixed"
                            else None
                        ),
                        is_bonus=is_bonus,
                        eligibility=description or ("Bonus/限定产品" if is_bonus else ""),
                        source="OKX Earn website API",
                        product_id=f"{asset}-{item.get('productsType', '')}-{item.get('type', '')}-{index}",
                    )
                )
        return results

    @staticmethod
    def _product_type(item: dict[str, Any]) -> str:
        if item.get("productsType") == 1 or item.get("type") == 1:
            return "flexible"
        term = decimal((item.get("term") or {}).get("value"))
        return "fixed" if term > 1 else "flexible"

    @staticmethod
    def _deduplicate(offers: list[EarnOffer]) -> list[EarnOffer]:
        seen: set[tuple[str, str, str, str, str]] = set()
        result: list[EarnOffer] = []
        for offer in offers:
            key = (
                offer.asset,
                offer.product_type,
                str(offer.apr_percent),
                offer.eligibility,
                offer.status,
            )
            if key not in seen:
                seen.add(key)
                result.append(offer)
        return result

    @staticmethod
    def _is_unsupported(error: Exception) -> bool:
        text = str(error).lower()
        return "parameter ccy error" in text or "doesn't support this crypto" in text
