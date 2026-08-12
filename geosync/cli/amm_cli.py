# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import argparse
import asyncio
import csv
import re
from pathlib import Path
from typing import AsyncIterator, Tuple

from prometheus_client import start_http_server

from analytics.amm_metrics import publish_metrics, timed_update
from core.neuro.amm import AdaptiveMarketMind, AMMConfig

REQUIRED_COLUMNS: Tuple[str, ...] = ("x", "R", "kappa")
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,15}$")
_TIMEFRAME_RE = re.compile(r"^(\d+)(s|m|h|d|w)$")


class CSVValidationError(ValueError):
    """Raised when CSV rows fail validation."""


def _existing_csv(path_text: str) -> Path:
    """Ensure the provided path exists and points to a readable CSV file."""

    path = Path(path_text).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(
            f"CSV path '{path_text}' does not exist or is not a file. "
            "Provide a valid dataset with the required indicator columns."
        )
    return path


def _valid_port(value: str) -> int:
    """Return a safe TCP port in the dynamic range."""

    try:
        port = int(value)
    except ValueError as exc:  # pragma: no cover - argparse prevents float paths
        raise argparse.ArgumentTypeError("Metrics port must be an integer") from exc

    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            "Metrics port should be between 1024 and 65535 to avoid privileged or invalid ports."
        )
    return port


def _valid_symbol(value: str) -> str:
    upper = value.upper()
    if not _SYMBOL_RE.match(upper):
        raise argparse.ArgumentTypeError(
            "Symbol must be 3-15 alphanumeric characters (e.g. BTCUSDT)."
        )
    return upper


def _valid_timeframe(value: str) -> str:
    if not _TIMEFRAME_RE.match(value):
        raise argparse.ArgumentTypeError(
            "Timeframe must follow <number><unit> (s, m, h, d, w). Examples: 1m, 4h, 1d."
        )
    return value


def _parse_required(row: dict[str, str | None], column: str, line_no: int) -> float:
    raw = row.get(column)
    if raw is None or raw.strip() == "":
        raise CSVValidationError(
            f"Column '{column}' is required but empty at line {line_no}. Provide numeric values."
        )
    try:
        return float(raw)
    except ValueError as exc:
        raise CSVValidationError(
            f"Column '{column}' must be numeric at line {line_no}; got '{raw}'."
        ) from exc


def _parse_optional(row: dict[str, str | None], column: str) -> float | None:
    raw = row.get(column)
    if raw is None or raw.strip() == "":
        return None
    return float(raw)


async def stream_csv(
    path: Path,
) -> AsyncIterator[Tuple[float, float, float, float | None]]:
    """Yield validated indicator tuples from a CSV file."""

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = [col for col in REQUIRED_COLUMNS if col not in columns]
        if missing:
            raise CSVValidationError(
                "Missing required columns: "
                + ", ".join(missing)
                + ". Expected headers: x, R, kappa and optional H."
            )

        for line_no, row in enumerate(reader, start=2):  # start=2 accounts for header line
            x = _parse_required(row, "x", line_no)
            R = _parse_required(row, "R", line_no)
            kappa = _parse_required(row, "kappa", line_no)
            try:
                H = _parse_optional(row, "H")
            except ValueError as exc:
                raise CSVValidationError(
                    f"Optional column 'H' must be numeric at line {line_no}; got '{row.get('H')}'."
                ) from exc
            yield x, R, kappa, H


async def run(path: Path, symbol: str, tf: str, metrics_port: int) -> None:
    try:
        start_http_server(metrics_port)
    except OSError as exc:
        raise ValueError(
            f"Unable to start Prometheus metrics endpoint on port {metrics_port}: {exc}"
        ) from exc

    amm = AdaptiveMarketMind(AMMConfig())
    async for x, R, kappa, H in stream_csv(path):
        with timed_update(symbol, tf):
            out = await amm.aupdate(x, R, kappa, H)
        publish_metrics(symbol, tf, out, k=amm.gain, theta=amm.threshold, q_hi=None)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Stream AdaptiveMarketMind metrics from a validated CSV feed. "
            "Sanity checks reject missing columns and unsafe parameter ranges."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Tip: generate a starter CSV via 'python scripts/sample_feed.py --out data.csv' "
            "and keep risk metrics bounded before enabling live publishing."
        ),
    )
    ap.add_argument(
        "--csv",
        type=_existing_csv,
        required=True,
        help="CSV with columns: x,R,kappa[,H]",
    )
    ap.add_argument(
        "--symbol",
        type=_valid_symbol,
        default="BTCUSDT",
        help="Trading symbol (uppercase alphanumeric)",
    )
    ap.add_argument(
        "--tf",
        type=_valid_timeframe,
        default="1m",
        help="Timeframe notation <number><unit>, e.g. 1m",
    )
    ap.add_argument(
        "--metrics-port",
        type=_valid_port,
        default=9095,
        help="Prometheus metrics port (avoid privileged ports)",
    )
    args = ap.parse_args()

    try:
        asyncio.run(run(args.csv, args.symbol, args.tf, args.metrics_port))
    except CSVValidationError as exc:
        ap.exit(2, f"CSV validation error: {exc}\n")
    except ValueError as exc:
        ap.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
