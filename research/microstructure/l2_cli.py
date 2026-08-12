"""Shared CLI helpers for the L2 analysis scripts.

Every `scripts/run_l2_*.py` duplicates the same six-block preamble:

    · argparse with --data-dir, --symbols, --output, --log-level
    · symbol-tuple parsing
    · logging.basicConfig
    · data_dir existence check
    · load_parquets(data_dir, symbols) with "no shards" error
    · build_feature_frame(frames, symbols) with ValueError guard

This module collapses all six into three helpers:

    add_common_args(parser, output_default)   — mutates parser in place
    setup_logging(log_level)                   — standard format
    load_substrate(data_dir, symbols_csv)      — returns FeatureFrame or
                                                  raises SubstrateError

Scripts become shorter, their argparse contract becomes uniform, and
the CLI-discoverability test (test_l2_coherence_cli_discoverability)
keeps passing because every script still exposes --data-dir + --output.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from research.microstructure.l2_schema import DEFAULT_SYMBOLS

if TYPE_CHECKING:
    from research.microstructure.killtest import FeatureFrame


class SubstrateError(RuntimeError):
    """Raised when L2 substrate cannot be loaded into a FeatureFrame."""


@dataclass(frozen=True)
class LoadedSubstrate:
    features: "FeatureFrame"
    frames: dict[str, object]


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    output_default: Path,
) -> None:
    """Attach the L2-standard arguments to an existing argparse parser.

    Standard arguments:
        --data-dir     default data/binance_l2_perp
        --symbols      default DEFAULT_SYMBOLS comma-joined
        --output       default output_default (caller-supplied)
        --log-level    default INFO
    """
    parser.add_argument("--data-dir", type=Path, default=Path("data/binance_l2_perp"))
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--output", type=Path, default=output_default)
    parser.add_argument("--log-level", default="INFO")


def setup_logging(log_level: str) -> None:
    """Apply the canonical L2 logging format at the chosen level."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def parse_symbols(symbols_csv: str) -> tuple[str, ...]:
    """Split CSV string into UPPER-cased symbol tuple, preserving order."""
    return tuple(s.strip().upper() for s in str(symbols_csv).split(",") if s.strip())


def load_substrate(data_dir: Path, symbols_csv: str) -> LoadedSubstrate:
    """Load L2 parquet shards and build the aligned FeatureFrame.

    Raises SubstrateError when the data directory is missing, contains no
    parquet shards, or when the resulting overlap is insufficient.
    """
    # Imported lazily so this module stays importable without pandas etc.
    from research.microstructure.killtest import (
        _load_parquets as load_parquets,
    )
    from research.microstructure.killtest import (
        build_feature_frame,
    )

    symbols = parse_symbols(symbols_csv)
    if not data_dir.exists():
        raise SubstrateError(f"data dir does not exist: {data_dir}")
    frames = load_parquets(data_dir, symbols)
    if not frames:
        raise SubstrateError(f"no parquet shards in {data_dir}")
    try:
        features = build_feature_frame(frames, symbols)
    except ValueError as exc:
        raise SubstrateError(f"insufficient overlap: {exc}") from exc
    return LoadedSubstrate(features=features, frames=frames)
