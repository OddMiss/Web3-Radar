from __future__ import annotations

import argparse
import logging
import sys

from .config import Settings
from .monitor import RadarMonitor, healthcheck


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Web3 Radar stablecoin earn-rate monitor")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run the hourly monitor")
    run.add_argument("--once", action="store_true", help="run one cycle and exit")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="collect and print without sending to Telegram",
    )
    subparsers.add_parser("healthcheck", help="verify that recent cycles succeeded")
    return parser


def main(argv: list[str] | None = None) -> None:
    # Windows PowerShell may still expose a legacy GBK console encoding.
    # UTF-8 keeps Chinese text and Telegram preview emoji printable.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        settings = Settings.from_env()
        if args.command == "healthcheck":
            ok, message = healthcheck(settings.health_file_path, settings.interval_seconds)
            print(message)
            raise SystemExit(0 if ok else 1)
        settings.validate_for_run(require_telegram=not args.dry_run)
        monitor = RadarMonitor(settings)
        if args.once or args.dry_run:
            messages = monitor.run_once(send=not args.dry_run)
            if args.dry_run:
                print("\n\n--- TELEGRAM MESSAGE ---\n\n".join(messages))
            return
        monitor.run_forever()
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
