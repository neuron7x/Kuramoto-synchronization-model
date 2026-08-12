#!/usr/bin/env python3
"""Hurst exponent CLI — scale-free cross-check for spectral β.

Consumes one L2 substrate; produces a Hurst JSON that independently
confirms or contradicts the spectral redness finding (PR #271, β=+1.80):

    β ≈ 2.0  ↔  H ≈ 1.5  (Brownian / random-walk persistence)

Writes results/L2_HURST.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.microstructure.hurst import (
    DEFAULT_MAX_SCALE_FRAC,
    DEFAULT_MIN_SCALE,
    DEFAULT_N_SCALES,
    dfa_hurst,
)
from research.microstructure.killtest import cross_sectional_ricci_signal
from research.microstructure.l2_cli import (
    SubstrateError,
    add_common_args,
    load_substrate,
    setup_logging,
)

_log = logging.getLogger("l2_hurst")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_HURST.json"))
    parser.add_argument("--min-scale", type=int, default=DEFAULT_MIN_SCALE)
    parser.add_argument("--max-scale-frac", type=float, default=DEFAULT_MAX_SCALE_FRAC)
    parser.add_argument("--n-scales", type=int, default=DEFAULT_N_SCALES)
    args = parser.parse_args()

    setup_logging(str(args.log_level))

    try:
        loaded = load_substrate(Path(args.data_dir), str(args.symbols))
    except SubstrateError as exc:
        _log.error("%s", exc)
        return 2
    features = loaded.features

    signal = cross_sectional_ricci_signal(features.ofi)
    report = dfa_hurst(
        signal,
        min_scale=int(args.min_scale),
        max_scale_frac=float(args.max_scale_frac),
        n_scales=int(args.n_scales),
    )

    payload: dict[str, Any] = {
        "n_rows": features.n_rows,
        "n_symbols": features.n_symbols,
        "min_scale": int(args.min_scale),
        "max_scale_frac": float(args.max_scale_frac),
        "n_scales": int(args.n_scales),
        "report": asdict(report),
    }
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "Hurst H=%.4f R²=%.4f verdict=%s (n_scales=%d, n=%d)",
        report.hurst_exponent,
        report.r_squared,
        report.verdict,
        len(report.scales),
        report.n_samples_used,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
