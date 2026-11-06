from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from web3_radar.formatting import format_report
from web3_radar.models import EarnOffer, ProviderResult, RateTier


class FormattingTests(unittest.TestCase):
    def test_report_exposes_small_balance_bonus_cap(self) -> None:
        offer = EarnOffer(
            exchange="Example",
            asset="USDT",
            product_type="flexible",
            product_name="Savings",
            apr_percent=Decimal("8"),
            is_bonus=True,
            tiers=(
                RateTier(Decimal("0"), Decimal("300"), Decimal("8"), True, "小额高息档"),
                RateTier(Decimal("300"), None, Decimal("2")),
            ),
        )
        messages = format_report(
            datetime(2026, 11, 6, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            [ProviderResult("Example", (offer,))],
        )
        text = "\n".join(messages)
        self.assertIn("0–300: 8%", text)
        self.assertIn("300–∞: 2%", text)
        self.assertIn("Bonus/限定", text)


if __name__ == "__main__":
    unittest.main()
