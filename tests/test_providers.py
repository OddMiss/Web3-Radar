from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from web3_radar.config import Settings
from web3_radar.providers.binance import BinanceProvider
from web3_radar.providers.bitget import BitgetProvider
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


class FakeWebHttp:
    def __init__(self, html: str) -> None:
        self.html = html

    def get_text(self, url: str, *, headers=None) -> str:
        return self.html

    def post_json(self, url: str, *, data, headers=None):
        marker = "window.__ZEUS_REACT_QUERY_STATE__ = "
        raw = self.html.split(marker, 1)[1].split("</script>", 1)[0].strip().removesuffix(";")
        state = json.loads(raw)
        list_data = state["queries"][0]["state"]["data"]["listData"]
        return {"code": "200", "data": list_data}


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


class BitgetProviderTests(unittest.TestCase):
    def test_public_webpage_needs_no_credentials_and_parses_tiers(self) -> None:
        state = {
            "queries": [
                {
                    "queryKey": ["earning-overview-prefetch", "/finance"],
                    "state": {
                        "data": {
                            "listData": [
                                {
                                    "coinName": "USDT",
                                    "bizLineProductList": [
                                        {
                                            "secondBizLine": "Savings",
                                            "productLevel": 1,
                                            "productList": [
                                                {
                                                    "id": "964334561256718336",
                                                    "coinName": "USDT",
                                                    "periodType": 1,
                                                    "period": 0,
                                                    "productLevel": 1,
                                                    "status": 2,
                                                    "visibleApy": True,
                                                    "maxApy": "11.61",
                                                    "apyList": [
                                                        {
                                                            "apy": "11.61",
                                                            "minStepValue": "0",
                                                            "maxStepValue": "1000",
                                                        },
                                                        {
                                                            "apy": "3.61",
                                                            "minStepValue": "1000",
                                                            "maxStepValue": "120000000",
                                                        },
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                }
            ]
        }
        html = (
            "<html><script>window.__ZEUS_REACT_QUERY_STATE__ = "
            + json.dumps(state)
            + ";</script></html>"
        )
        result = BitgetProvider(settings(), FakeWebHttp(html)).fetch()
        self.assertEqual(result.error, "")
        self.assertEqual(len(result.offers), 1)
        offer = result.offers[0]
        self.assertEqual(str(offer.apr_percent), "11.61")
        self.assertEqual(str(offer.tiers[0].max_amount), "1000")
        self.assertTrue(offer.tiers[0].is_bonus)
        self.assertEqual(offer.source, "Bitget public Earn webpage")

    def test_web_status_marks_ended_and_sold_out_products(self) -> None:
        self.assertEqual(BitgetProvider._web_status(2), "available")
        self.assertEqual(BitgetProvider._web_status(4), "sold_out")
        self.assertEqual(BitgetProvider._web_status(6), "sold_out")


if __name__ == "__main__":
    unittest.main()
