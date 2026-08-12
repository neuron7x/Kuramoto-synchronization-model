#!/usr/bin/env python3
"""Deterministic end-to-end runner for tasks 7..17."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Step:
    name: str
    cmd: list[str]
    returncode: int
    ok: bool


def _run(name: str, cmd: list[str]) -> Step:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip())
    return Step(name=name, cmd=cmd, returncode=proc.returncode, ok=proc.returncode == 0)


def main() -> int:
    py = "python"
    steps = [
        ("task7_fetch", [py, "scripts/fetch_dukascopy_l2.py"]),
        (
            "task8_ofi",
            [
                py,
                "research/kernels/ofi_unity_live.py",
                "--source",
                "dukascopy",
                "--input-csv",
                "data/dukascopy/xauusd_l2_hourly.csv",
                "--output",
                "results/ofi_unity_dukascopy_verdict.json",
            ],
        ),
        (
            "task9_neurophase",
            [
                py,
                "research/kernels/neurophase_bridge.py",
                "--input-csv",
                "data/dukascopy/xauusd_l2_hourly.csv",
                "--output-csv",
                "results/neurophase_gate_history.csv",
                "--window",
                "256",
                "--threshold",
                "0.65",
            ],
        ),
        (
            "task11_ricci_spread",
            [
                py,
                "research/kernels/ricci_on_spread.py",
                "--input-csv",
                "data/dukascopy/xauusd_l2_hourly.csv",
                "--output-json",
                "results/ricci_on_spread_verdict.json",
            ],
        ),
        (
            "task12_plv",
            [
                py,
                "research/kernels/plv_market_spread.py",
                "--input-csv",
                "data/dukascopy/xauusd_l2_hourly.csv",
                "--output-json",
                "results/plv_spread_market_verdict.json",
            ],
        ),
        (
            "task13_stress",
            [
                py,
                "research/kernels/spread_stress_detector.py",
                "--input-csv",
                "data/dukascopy/xauusd_l2_hourly.csv",
                "--output-json",
                "results/spread_stress_verdict.json",
            ],
        ),
        (
            "task14_regime",
            [
                py,
                "research/kernels/ricci_regime_conditioned.py",
                "--input-csv",
                "data/dukascopy/xauusd_l2_hourly.csv",
                "--output-json",
                "results/ricci_regime_verdict.json",
            ],
        ),
        (
            "task15_horizon",
            [
                py,
                "research/kernels/horizon_sweep.py",
                "--input-csv",
                "data/dukascopy/xauusd_l2_hourly.csv",
                "--output-json",
                "results/horizon_sweep_verdict.json",
            ],
        ),
        (
            "task16_combiner",
            [
                py,
                "research/kernels/signal_combiner.py",
                "--input-csv",
                "data/dukascopy/xauusd_l2_hourly.csv",
                "--output-json",
                "results/signal_combiner_verdict.json",
            ],
        ),
        (
            "task17_final",
            [
                py,
                "research/askar/closing_report.py",
                "--results-dir",
                "results",
                "--output-json",
                "results/FINAL_REPORT.json",
            ],
        ),
    ]

    out: list[Step] = []
    for name, cmd in steps:
        print(f"\n=== {name} ===")
        step = _run(name, cmd)
        out.append(step)
        if not step.ok:
            break

    manifest = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "steps": [asdict(s) for s in out],
        "all_ok": all(s.ok for s in out),
    }
    Path("results").mkdir(exist_ok=True)
    Path("results/RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
