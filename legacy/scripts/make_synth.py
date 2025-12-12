"""CLI for generating synthetic tick data used in NeuroTrade PRO demos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from neuropro.synthetic import DEFAULT_DEMO_TICKS_PATH, generate_demo_ticks


def make_synth(n: int = 15000, seed: int = 7, path: Path | None = None) -> Path:
    """Generate the demo tick dataset and return the materialised path."""

    target = path or DEFAULT_DEMO_TICKS_PATH
    return generate_demo_ticks(target, n=n, seed=seed)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n",
        type=int,
        default=15000,
        help="Number of ticks to generate (default: 15000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Seed for the random number generator (default: 7)",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_DEMO_TICKS_PATH,
        help="Output location for the generated CSV (default: neuropro/data/sim_ticks.csv)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = make_synth(n=args.n, seed=args.seed, path=args.path)
    print("Saved", path)


if __name__ == "__main__":
    main()
