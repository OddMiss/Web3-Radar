from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_STABLECOINS = (
    "USDT",
    "USDC",
    "FDUSD",
    "USDE",
    "DAI",
    "PYUSD",
    "TUSD",
    "USDP",
    "USD1",
    "USDG",
    "RLUSD",
)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _get_int(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    stablecoins: tuple[str, ...]
    interval_seconds: int
    http_timeout_seconds: int
    database_path: Path
    health_file_path: Path
    telegram_bot_token: str
    telegram_chat_id: str
    binance_api_key: str
    binance_api_secret: str
    bitget_api_key: str
    bitget_api_secret: str
    bitget_api_passphrase: str
    binance_api_base: str
    binance_web_base: str
    bitget_api_base: str
    bybit_api_base: str
    okx_api_base: str

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        _load_dotenv(env_file or Path(".env"))
        assets = tuple(
            dict.fromkeys(
                part.strip().upper()
                for part in os.getenv("STABLECOINS", ",".join(DEFAULT_STABLECOINS)).split(",")
                if part.strip()
            )
        )
        if not assets:
            raise ValueError("STABLECOINS cannot be empty")
        return cls(
            stablecoins=assets,
            interval_seconds=_get_int("MONITOR_INTERVAL_SECONDS", 3600, 60),
            http_timeout_seconds=_get_int("HTTP_TIMEOUT_SECONDS", 20, 1),
            database_path=Path(os.getenv("DATABASE_PATH", "data/web3_radar.sqlite3")),
            health_file_path=Path(os.getenv("HEALTH_FILE_PATH", "data/last_run.json")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            binance_api_key=os.getenv("BINANCE_API_KEY", "").strip(),
            binance_api_secret=os.getenv("BINANCE_API_SECRET", "").strip(),
            bitget_api_key=os.getenv("BITGET_API_KEY", "").strip(),
            bitget_api_secret=os.getenv("BITGET_API_SECRET", "").strip(),
            bitget_api_passphrase=os.getenv("BITGET_API_PASSPHRASE", "").strip(),
            binance_api_base=os.getenv("BINANCE_API_BASE", "https://api.binance.com").rstrip("/"),
            binance_web_base=os.getenv("BINANCE_WEB_BASE", "https://www.binance.com").rstrip("/"),
            bitget_api_base=os.getenv("BITGET_API_BASE", "https://api.bitget.com").rstrip("/"),
            bybit_api_base=os.getenv("BYBIT_API_BASE", "https://api.bybit.com").rstrip("/"),
            okx_api_base=os.getenv("OKX_API_BASE", "https://www.okx.com").rstrip("/"),
        )

    def validate_for_run(self, *, require_telegram: bool = True) -> None:
        missing: list[str] = []
        if require_telegram and not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if require_telegram and not self.telegram_chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if missing:
            raise ValueError("missing required settings: " + ", ".join(missing))
