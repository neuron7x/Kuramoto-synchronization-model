#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generate synthetic AMM (Automated Market Maker) data for testing and development.

This script creates synthetic time series data with configurable regime changes,
useful for testing trading algorithms and market analysis tools.
"""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_PATH = Path("data/amm_synth.csv")
DEFAULT_NUM_SAMPLES = 5000
DEFAULT_SEED = 7


def generate_amm_data(
    n: int = DEFAULT_NUM_SAMPLES, seed: int = DEFAULT_SEED
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate synthetic AMM time series data with two regime phases.

    Args:
        n: Number of samples to generate
        seed: Random seed for reproducibility

    Returns:
        Tuple of (x, R, kappa, H) numpy arrays representing market state variables
    """
    rng = np.random.default_rng(seed)
    x = np.zeros(n, dtype=np.float32)
    R = np.zeros(n, dtype=np.float32)
    kappa = np.zeros(n, dtype=np.float32)
    H = np.zeros(n, dtype=np.float32)

    # Regime 1 -> 2 transition with higher volatility and synchronization
    for t in range(n):
        if t < n // 2:
            x[t] = rng.normal(0, 0.001)
            R[t] = 0.5 + 0.05 * rng.random()
            kappa[t] = 0.1 + 0.05 * rng.normal()
        else:
            x[t] = rng.normal(0, 0.004) + (0.02 if t % 100 < 2 else 0.0)
            R[t] = 0.65 + 0.05 * rng.random()
            kappa[t] = -0.1 + 0.05 * rng.normal()
        H[t] = max(0.0, abs(x[t]) * 150)

    return x, R, kappa, H


def write_csv(
    output_path: Path,
    n: int = DEFAULT_NUM_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> Path:
    """Generate and write synthetic AMM data to a CSV file.

    Args:
        output_path: Path where the CSV file will be written
        n: Number of samples to generate
        seed: Random seed for reproducibility

    Returns:
        Path to the written CSV file
    """
    LOGGER.info("Generating %d synthetic AMM samples (seed=%d) to %s", n, seed, output_path)

    x, R, kappa, H = generate_amm_data(n, seed)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["x", "R", "kappa", "H"])
        for i in range(len(x)):
            writer.writerow([float(x[i]), float(R[i]), float(kappa[i]), float(H[i])])

    LOGGER.info("Successfully wrote %d rows to %s", n, output_path)
    return output_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Command line arguments (None uses sys.argv)

    Returns:
        Parsed argument namespace
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output CSV file path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "-n",
        "--num-samples",
        type=int,
        default=DEFAULT_NUM_SAMPLES,
        help=f"Number of samples to generate (default: {DEFAULT_NUM_SAMPLES})",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for reproducibility (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point for the synthetic AMM data generator.

    Args:
        argv: Command line arguments (None uses sys.argv)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    args = parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    try:
        output_path = write_csv(args.output, args.num_samples, args.seed)
        print(str(output_path))
        return 0
    except Exception as exc:
        LOGGER.error("Failed to generate synthetic data: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
