from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from web3_radar.config import Settings
from web3_radar.providers.binance import BinanceProvider
from web3_radar.providers.bybit import BybitProvider
from web3_radar.providers.okx import OkxProvider


class FakeHttp:
    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses

    def get_json(self, url: str, *, params=None, headers=None):
        key = url
        if params and "category" in params:
            key += ":" + str(params["category"])
        return self.responses[key]


def settings() -> Settings:
    with TemporaryDirectory() as directory:
        env = Path(directory) / ".env"
        env.write_text("STABLECOINS=USDT\n", encoding="utf-8")
        previous = os.environ.pop("STABLECOINS", None)
        try:
            return Settings.from_env(env)
        finally:
            if previous is not None:
                os.environ["STABLECOINS"] = previous
            else:
                os.environ.pop("STABLECOINS", None)


class BinanceProviderTests(unittest.TestCase):
    def test_parses_bonus_tier_and_base_tail(self) -> None:
        config = settings()
        url = (
            f"{config.binance_web_base}/bapi/earn/v1/friendly/"
            "finance-earn/simple/product/simpleEarnProducts"
        )
        http = FakeHttp(
            {
                url: {
                    "code": "000000",
                    "data": {
                        "list": [
                            {
                                "asset": "USDT",
                                "productDetailList": [
                                    {
                                        "productId": "USDT001",
                                        "productType": "LENDING_FLEXIBLE",
                                        "status": "ENABLE",
                                        "marketApr": "0.0365",
                                        "apy": "0.1165",
                                        "minPurchaseAmount": "0.01",
                                        "apyTierOption": [
                                            {
                                                "beginAmount": "0",
                                                "endAmount": "1000",
                                                "ratio": "0.08",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    },
                }
            }
        )
        result = BinanceProvider(config, http).fetch()
        self.assertEqual(len(result.offers), 1)
        offer = result.offers[0]
        self.assertEqual(str(offer.apr_percent), "11.6500")
        self.assertEqual(len(offer.tiers), 2)
        self.assertEqual(str(offer.tiers[0].apr_percent), "11.6500")
        self.assertEqual(str(offer.tiers[1].apr_percent), "3.6500")


class BybitProviderTests(unittest.TestCase):
    def test_parses_current_tier_fields(self) -> None:
        config = settings()
        flexible_url = f"{config.bybit_api_base}/v5/earn/product:FlexibleSaving"
        fixed_url = f"{config.bybit_api_base}/v5/earn/fixed-term/product"
        http = FakeHttp(
            {
                flexible_url: {
                    "retCode": 0,
                    "result": {
                        "list": [
                            {
                                "coin": "USDT",
                                "estimateApr": "2.25%",
                                "status": "Available",
                                "minStakeAmount": "1",
                                "maxStakeAmount": "100000000",
                                "productId": "1",
                                "tierAprDetails": [
                                    {"min": "0", "max": "100", "estimateApr": "7.25%"},
                                    {"min": "100", "max": "-1", "estimateApr": "2.25%"},
                                ],
                            }
                        ]
                    },
                },
                fixed_url: {"retCode": 0, "result": {"list": []}},
            }
        )
        result = BybitProvider(config, http).fetch()
        self.assertEqual(len(result.offers), 1)
        self.assertEqual(str(result.offers[0].apr_percent), "7.25")
        self.assertEqual(str(result.offers[0].tiers[0].apr_percent), "7.25")
        self.assertTrue(result.offers[0].is_bonus)

    def test_unsupported_coin_is_not_reported_as_outage(self) -> None:
        self.assertTrue(BybitProvider._is_unsupported(RuntimeError("Invalid coin")))
        self.assertTrue(OkxProvider._is_unsupported(RuntimeError("Parameter ccy error")))


if __name__ == "__main__":
    unittest.main()
