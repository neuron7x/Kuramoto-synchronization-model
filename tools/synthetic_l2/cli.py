# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Minimal CLI for the synthetic L2 generator.

Example
-------
::

    python -m tools.synthetic_l2 --n 64 --levels 5 --regime pareto \\
        --seed 20260425 --out /tmp/snapshot.npz

Output is a NumPy ``.npz`` archive containing ``timestamp_ns``,
``bid_sizes``, ``ask_sizes`` and ``mid_prices`` — the four fields of
:class:`core.kuramoto.capital_weighted.L2DepthSnapshot`.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast, get_args

import numpy as np

from .book_factory import MidPriceDistribution, RegimeName, synthesize_l2_snapshot

__all__ = ["build_parser", "main"]

_REGIME_CHOICES: Final[tuple[str, ...]] = get_args(RegimeName)
_MID_PRICE_CHOICES: Final[tuple[str, ...]] = get_args(MidPriceDistribution)


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser used by :func:`main`."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.synthetic_l2",
        description="Deterministic synthetic L2 order-book snapshot generator.",
    )
    parser.add_argument(
        "--n",
        dest="n_nodes",
        type=int,
        default=64,
        help="Number of instruments (default: 64).",
    )
    parser.add_argument(
        "--levels",
        dest="n_levels",
        type=int,
        default=5,
        help="Number of price levels per side (default: 5).",
    )
    parser.add_argument(
        "--regime",
        dest="regime",
        type=str,
        default="pareto",
        choices=_REGIME_CHOICES,
        help="Depth-mass concentration regime (default: pareto).",
    )
    parser.add_argument(
        "--mid-price",
        dest="mid_price_distribution",
        type=str,
        default="lognormal",
        choices=_MID_PRICE_CHOICES,
        help="Mid-price distribution (default: lognormal).",
    )
    parser.add_argument(
        "--timestamp-ns",
        dest="timestamp_ns",
        type=int,
        default=0,
        help="Snapshot timestamp in nanoseconds (default: 0).",
    )
    parser.add_argument(
        "--seed",
        dest="seed",
        type=int,
        default=20260425,
        help="Deterministic seed (default: 20260425).",
    )
    parser.add_argument(
        "--bid-share",
        dest="bid_share",
        type=float,
        default=0.5,
        help="Fraction of mass on the bid side (default: 0.5 = symmetric).",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        type=Path,
        required=True,
        help="Destination .npz path.",
    )
    return parser


def _resolve_regime(name: str) -> RegimeName:
    if name not in _REGIME_CHOICES:
        # bounds: argparse 'choices' already enforces this; defensive guard
        # keeps the type-narrowing visible to mypy.
        raise ValueError(f"unknown regime {name!r}")
    return cast(RegimeName, name)


def _resolve_mid_price(name: str) -> MidPriceDistribution:
    if name not in _MID_PRICE_CHOICES:
        raise ValueError(f"unknown mid_price_distribution {name!r}")
    return cast(MidPriceDistribution, name)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Parameters
    ----------
    argv:
        Optional argv override (used by tests). ``None`` defers to
        ``sys.argv[1:]``.

    Returns
    -------
    int
        Process exit code: ``0`` on success.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    snapshot = synthesize_l2_snapshot(
        n_nodes=int(args.n_nodes),
        n_levels=int(args.n_levels),
        regime=_resolve_regime(str(args.regime)),
        mid_price_distribution=_resolve_mid_price(str(args.mid_price_distribution)),
        timestamp_ns=int(args.timestamp_ns),
        seed=int(args.seed),
        bid_share=float(args.bid_share),
    )

    out_path: Path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        out_path,
        timestamp_ns=np.int64(snapshot.timestamp_ns),
        bid_sizes=snapshot.bid_sizes,
        ask_sizes=snapshot.ask_sizes,
        mid_prices=snapshot.mid_prices,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via subprocess in tests.
    raise SystemExit(main())
