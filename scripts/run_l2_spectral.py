#!/usr/bin/env python3
"""Spectral CLI — Welch PSD + dominant period + redness slope on κ_min."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from research.microstructure.killtest import cross_sectional_ricci_signal
from research.microstructure.l2_cli import (
    SubstrateError,
    add_common_args,
    load_substrate,
    setup_logging,
)
from research.microstructure.spectral import (
    DEFAULT_SEGMENT_SEC,
    spectral_report,
)

_log = logging.getLogger("l2_spectral")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_SPECTRAL.json"))
    parser.add_argument("--segment-sec", type=int, default=DEFAULT_SEGMENT_SEC)
    parser.add_argument("--fs-hz", type=float, default=1.0)
    args = parser.parse_args()

    setup_logging(str(args.log_level))

    try:
        loaded = load_substrate(Path(args.data_dir), str(args.symbols))
    except SubstrateError as exc:
        _log.error("%s", exc)
        return 2
    features = loaded.features

    signal = cross_sectional_ricci_signal(features.ofi)
    report = spectral_report(
        signal,
        fs_hz=float(args.fs_hz),
        segment_sec=int(args.segment_sec),
    )

    # Trim stored PSD arrays to avoid a mega-json; expose top-N highest-power bins.
    psd_arr = list(report.psd)
    freq_arr = list(report.frequencies_hz)
    top_n = min(32, len(psd_arr))
    sort_idx = sorted(range(len(psd_arr)), key=lambda i: -psd_arr[i])[:top_n]
    top_bins = [
        {
            "freq_hz": freq_arr[i],
            "period_sec": (1.0 / freq_arr[i] if freq_arr[i] > 0 else None),
            "psd": psd_arr[i],
        }
        for i in sort_idx
    ]

    payload = {
        "n_rows": features.n_rows,
        "fs_hz": float(args.fs_hz),
        "segment_sec": int(args.segment_sec),
        "dominant_period_sec": report.dominant_period_sec,
        "dominant_peak_power": report.dominant_peak_power,
        "redness_slope_beta": report.redness_slope_beta,
        "redness_intercept": report.redness_intercept,
        "regime_verdict": report.regime_verdict,
        "top_power_bins": top_bins,
        "n_psd_bins": len(psd_arr),
    }

    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)
    _log.info(
        "dominant_period=%ss peak_power=%s  redness β=%.3f verdict=%s",
        report.dominant_period_sec,
        report.dominant_peak_power,
        report.redness_slope_beta,
        report.regime_verdict,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
