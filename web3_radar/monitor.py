from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .formatting import format_report
from .http import HttpClient
from .models import ProviderResult
from .providers import BinanceProvider, BitgetProvider, BybitProvider, OkxProvider
from .storage import SnapshotStore
from .telegram import TelegramClient


LOGGER = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")


class RadarMonitor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpClient(timeout=settings.http_timeout_seconds)
        self.providers = (
            BinanceProvider(settings, self.http),
            OkxProvider(settings, self.http),
            BitgetProvider(settings, self.http),
            BybitProvider(settings, self.http),
        )
        self.store = SnapshotStore(settings.database_path)
        self.telegram = TelegramClient(
            self.http, settings.telegram_bot_token, settings.telegram_chat_id
        )

    def collect(self) -> tuple[datetime, list[ProviderResult]]:
        observed_at = datetime.now(SHANGHAI)
        results: list[ProviderResult] = []
        for provider in self.providers:
            LOGGER.info("collecting %s", provider.name)
            try:
                results.append(provider.fetch())
            except Exception as exc:
                LOGGER.exception("provider %s failed", provider.name)
                results.append(ProviderResult(provider.name, (), str(exc)))
        return observed_at, results

    def run_once(self, *, send: bool = True) -> list[str]:
        observed_at, results = self.collect()
        self.store.initialize()
        run_id = self.store.save(observed_at, results)
        messages = format_report(observed_at, results)
        if send:
            for message in messages:
                self.telegram.send(message)
        self._write_health(
            {
                "status": "ok",
                "run_id": run_id,
                "completed_at": datetime.now(SHANGHAI).isoformat(),
                "offer_count": sum(len(result.offers) for result in results),
                "provider_errors": {
                    result.exchange: result.error for result in results if result.error
                },
                "telegram_sent": send,
            }
        )
        return messages

    def run_forever(self) -> None:
        while True:
            started = time.monotonic()
            try:
                self.run_once(send=True)
            except Exception as exc:
                LOGGER.exception("monitor cycle failed")
                self._write_health(
                    {
                        "status": "error",
                        "completed_at": datetime.now(SHANGHAI).isoformat(),
                        "error": str(exc),
                    }
                )
            elapsed = time.monotonic() - started
            sleep_seconds = max(1, self.settings.interval_seconds - elapsed)
            LOGGER.info("next cycle in %.0f seconds", sleep_seconds)
            time.sleep(sleep_seconds)

    def _write_health(self, payload: dict[str, object]) -> None:
        path = self.settings.health_file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)


def healthcheck(path: Path, interval_seconds: int) -> tuple[bool, str]:
    if not path.exists():
        return False, f"health file missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        completed_at = datetime.fromisoformat(str(payload["completed_at"]))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return False, f"invalid health file: {exc}"
    age = (datetime.now(SHANGHAI) - completed_at.astimezone(SHANGHAI)).total_seconds()
    maximum_age = max(interval_seconds * 2.5, 7200)
    if payload.get("status") != "ok":
        return False, f"last run failed: {payload.get('error', 'unknown error')}"
    if age > maximum_age:
        return False, f"last successful run is stale ({age:.0f}s old)"
    return True, f"ok; last successful run {age:.0f}s ago"
