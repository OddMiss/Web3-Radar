from __future__ import annotations

import sqlite3
import unittest
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from web3_radar.models import EarnOffer, ProviderResult
from web3_radar.storage import SnapshotStore


class StorageTests(unittest.TestCase):
    def test_saves_snapshot_and_provider_error(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "radar.sqlite3"
            store = SnapshotStore(path)
            store.initialize()
            run_id = store.save(
                datetime.now(ZoneInfo("Asia/Shanghai")),
                [
                    ProviderResult(
                        "Example",
                        (
                            EarnOffer(
                                exchange="Example",
                                asset="USDT",
                                product_type="flexible",
                                product_name="Savings",
                                apr_percent=Decimal("3.5"),
                            ),
                        ),
                        "partial failure",
                    )
                ],
            )
            with closing(sqlite3.connect(path)) as connection:
                offer_count = connection.execute(
                    "SELECT COUNT(*) FROM offers WHERE run_id = ?", (run_id,)
                ).fetchone()[0]
                error_count = connection.execute(
                    "SELECT COUNT(*) FROM provider_errors WHERE run_id = ?", (run_id,)
                ).fetchone()[0]
            self.assertEqual(offer_count, 1)
            self.assertEqual(error_count, 1)


if __name__ == "__main__":
    unittest.main()
