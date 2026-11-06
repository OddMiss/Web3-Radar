from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .models import ProviderResult


class SnapshotStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        observed_at TEXT NOT NULL,
                        offer_count INTEGER NOT NULL,
                        error_count INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS offers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER NOT NULL REFERENCES runs(id),
                        exchange TEXT NOT NULL,
                        asset TEXT NOT NULL,
                        product_type TEXT NOT NULL,
                        product_id TEXT NOT NULL,
                        apr_percent TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_offers_lookup
                        ON offers(exchange, asset, product_type, run_id);
                    CREATE TABLE IF NOT EXISTS provider_errors (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER NOT NULL REFERENCES runs(id),
                        exchange TEXT NOT NULL,
                        error TEXT NOT NULL
                    );
                    """
                )

    def save(self, observed_at: datetime, results: list[ProviderResult]) -> int:
        offer_count = sum(len(result.offers) for result in results)
        error_count = sum(bool(result.error) for result in results)
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO runs(observed_at, offer_count, error_count) VALUES (?, ?, ?)",
                    (observed_at.isoformat(), offer_count, error_count),
                )
                run_id = int(cursor.lastrowid)
                for result in results:
                    if result.error:
                        connection.execute(
                            "INSERT INTO provider_errors(run_id, exchange, error) VALUES (?, ?, ?)",
                            (run_id, result.exchange, result.error),
                        )
                    for offer in result.offers:
                        connection.execute(
                            """
                            INSERT INTO offers(
                                run_id, exchange, asset, product_type, product_id,
                                apr_percent, status, payload_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                run_id,
                                offer.exchange,
                                offer.asset,
                                offer.product_type,
                                offer.product_id,
                                str(offer.apr_percent),
                                offer.status,
                                json.dumps(
                                    offer.to_dict(), ensure_ascii=False, separators=(",", ":")
                                ),
                            ),
                        )
        return run_id
