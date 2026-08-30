#!/usr/bin/env python3
"""CLI for the D-002L-P2 preregistered pre-outcome power gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from research.systemic_risk.d002l_power_gate import D002LPowerError, execute_from_paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1-status", type=Path, required=True)
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--calibration-noise", type=Path, required=True)
    ap.add_argument("--effect-prior", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ns = ap.parse_args()
    try:
        result = execute_from_paths(ns.p1_status, ns.registry, ns.calibration_noise, ns.effect_prior)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, D002LPowerError) else f"{type(exc).__name__}:{exc}"
        sys.stderr.write(f"D002L-P2 BLOCKED: {reason}\n")
        return 10
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "TERMINAL_PASS" else 11


if __name__ == "__main__":
    raise SystemExit(main())
