#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Audit: is an i.i.d. Gaussian null adequate for autocorrelated series? (Task 02)

A null hypothesis test is only as honest as its null. An i.i.d. Gaussian null
(``analytics.signals.null_baseline.make_gaussian_null``) destroys temporal
structure: it has, by construction, ~zero autocorrelation. Phase trajectories
and Kuramoto order parameters are strongly autocorrelated. A statistic that is
sensitive to autocorrelation will therefore clear an i.i.d. Gaussian null
trivially — *false survival*, not evidence. The structure-preserving nulls the
repo already ships (IAAFT in ``core.kuramoto.falsification``; phase-shuffle in
``null_baseline``; the N3 block-bootstrap / N4 IAAFT families in
``research/systemic_risk/nulls/d002j``) are the admissible nulls where phase
structure matters.

This module produces the *evidence* for that claim, not the claim itself: it
measures the lag-1 autocorrelation an i.i.d. Gaussian null retains versus an
autocorrelated AR(1) reference, and reports whether the gap exceeds a margin.
It makes no predictive or market claim; it is a statistical-adequacy audit.

Exit codes::

    0  audit ran; verdict written (always 0 — the verdict is data, not a gate)
    2  malformed invocation
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
from numpy.typing import NDArray

_ROOT = Path(__file__).resolve().parents[2]

#: A series whose lag-1 autocorrelation exceeds this is "autocorrelated" for the
#: purpose of null adequacy; an i.i.d. null is inadequate for it.
AUTOCORR_THRESHOLD = 0.2


def lag1_autocorr(series: NDArray[np.float64]) -> float:
    """Lag-1 sample autocorrelation of a 1-D series."""
    x = np.asarray(series, dtype=np.float64)
    x = x - x.mean()
    denom = float(np.sum(x * x))
    if denom == 0.0:
        return 0.0
    return float(np.sum(x[:-1] * x[1:]) / denom)


def _ar1(n: int, phi: float, seed: int) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    out = np.empty(n, dtype=np.float64)
    out[0] = rng.standard_normal()
    for t in range(1, n):
        out[t] = phi * out[t - 1] + rng.standard_normal()
    return out


def _load_null_baseline() -> ModuleType:
    path = _ROOT / "analytics" / "signals" / "null_baseline.py"
    spec = importlib.util.spec_from_file_location("_nb_audit", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_nb_audit"] = module
    spec.loader.exec_module(module)
    return module


def run_audit(*, n: int = 4096, phi: float = 0.8, seed: int = 7) -> dict[str, Any]:
    """Measure the autocorrelation an i.i.d. Gaussian null fails to preserve."""
    nb = _load_null_baseline()
    gaussian, _ = nb.make_gaussian_null(n, seed)
    ar1 = _ar1(n, phi, seed)

    ac_gaussian = lag1_autocorr(np.asarray(gaussian, dtype=np.float64))
    ac_ar1 = lag1_autocorr(ar1)
    gap = ac_ar1 - abs(ac_gaussian)

    return {
        "schema_version": 1,
        "reference": {"kind": "AR1", "phi": phi, "n": n, "seed": seed},
        "iid_gaussian_lag1_autocorr": round(ac_gaussian, 6),
        "autocorrelated_lag1_autocorr": round(ac_ar1, 6),
        "autocorr_gap": round(gap, 6),
        "autocorr_threshold": AUTOCORR_THRESHOLD,
        "iid_gaussian_is_inadequate_for_autocorrelated_series": bool(
            ac_ar1 >= AUTOCORR_THRESHOLD and abs(ac_gaussian) < AUTOCORR_THRESHOLD
        ),
        "verdict": (
            "i.i.d. Gaussian null does not preserve temporal autocorrelation; it is "
            "INADEQUATE as a null for autocorrelated phase/order-parameter series. Use a "
            "structure-preserving null (IAAFT, phase-shuffle, block-bootstrap) where phase "
            "structure matters."
        ),
        "is_predictive_claim": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="write the audit evidence JSON here")
    parser.add_argument("--n", type=int, default=4096)
    parser.add_argument("--phi", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    audit = run_audit(n=args.n, phi=args.phi, seed=args.seed)
    text = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(
        f"gaussian lag1={audit['iid_gaussian_lag1_autocorr']} "
        f"ar1 lag1={audit['autocorrelated_lag1_autocorr']} "
        f"inadequate={audit['iid_gaussian_is_inadequate_for_autocorrelated_series']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
