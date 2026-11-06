"""Run Web3 Radar directly from a source checkout.

Examples:
    python run.py
    python run.py --once
    python run.py --once --dry-run
    python run.py healthcheck
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
os.chdir(PROJECT_ROOT)

from web3_radar.cli import main  # noqa: E402  (import after fixing the working directory)


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if not arguments:
        arguments = ["run"]
    elif arguments[0] in {"--once", "--dry-run"}:
        arguments = ["run", *arguments]
    main(arguments)
