#!/usr/bin/env python3
"""Render the three canonical L2-edge figures from results JSON artifacts.

Pure transformation: reads results/*.json + gate_fixtures/*.json;
writes results/figures/fig{1,2,3}_*.png. Deterministic — same input
yields byte-identical output.

    fig1_signal_validation.png — κ_min existence + robustness
    fig2_dynamics.png          — spectral + DFA + diurnal + autocorr
    fig3_coupling.png          — TE + CTE + Markov + break-even
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from research.microstructure.visualize import render_all

_log = logging.getLogger("render_l2_figures")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/figures"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    if not results_dir.exists():
        _log.error("results dir does not exist: %s", results_dir)
        return 2

    try:
        paths = render_all(results_dir, output_dir)
    except FileNotFoundError as exc:
        _log.error("artifact missing: %s", exc)
        return 2

    _log.info("fig0 → %s", paths.cover)
    _log.info("fig1 → %s", paths.signal_validation)
    _log.info("fig2 → %s", paths.dynamics)
    _log.info("fig3 → %s", paths.coupling)
    _log.info("fig4 → %s", paths.stability)
    return 0


if __name__ == "__main__":
    sys.exit(main())
