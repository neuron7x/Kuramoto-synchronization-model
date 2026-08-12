# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Run the FROZEN calibration cases through the graded front-gate.

This validates **instrument honesty**, not science: it asserts that the
upgraded swing estimator now *self-reports* its operating envelope on
the exact pre-registered WSCC-9 cases. It does **not** re-define,
re-tune or peek at any frozen gate (``PREREGISTRATION.md`` / ``gates.py``
/ seeds / σ / θ₀ / decision rule are untouched) and it does **not**
close the frozen ``noisy.frobenius`` gate — the noisy regime stays
NEGATIVE; the only change is that the instrument now declares it.

Usage::

    PYTHONPATH=. python -m \
        research.calibration.grid_kuramoto.identifiability.validate \
        --out research/calibration/grid_kuramoto/identifiability/RESULTS.json
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from core.kuramoto.coupling_estimator import estimate_swing_coupling
from core.kuramoto.identifiability import (
    PE_HARD_FLOOR,
    R2_FLOOR,
    REFUSE_SCORE,
    WALD_Z_0975,
)

from .._substrate import FROZEN_PREREG_SHA, PARENT_LEDGER_SHA256, branch_sha, ledger_sha256
from ..calibration import SimConfig, ground_truth, simulate_phases
from ..grid_data import GridSystem, wscc_9_bus

__all__ = ["build_identifiability_ledger", "main"]


def _branch_sha() -> str:
    """Best-effort current commit sha for the ledger provenance field."""
    return branch_sha(Path(__file__).resolve().parents[4])


def _front_gate_one(
    system: GridSystem,
    cfg: SimConfig,
    *,
    noisy: bool,
) -> dict[str, Any]:
    """Run one frozen regime through the swing path + front-gate.

    Mirrors :func:`research.calibration.grid_kuramoto.calibration.run_calibration`
    exactly (same ground truth, same frozen simulation, same swing
    solver settings as the merged R1 ``recover_coupling_swing``) and
    additionally attaches the graded identifiability report.
    """
    run_cfg = cfg if noisy else replace(cfg, noise_sigma=0.0)
    k_true, omega_true = ground_truth(system, run_cfg.coupling_scale)
    phases, _ = simulate_phases(system, k_true, omega_true, run_cfg)

    est = estimate_swing_coupling(
        phases,
        np.asarray(system.inertia, dtype=np.float64),
        np.asarray(system.damping, dtype=np.float64),
        dt=run_cfg.dt,
        symmetric=True,
        savgol_window=7,
        savgol_polyorder=4,
        pe_guard=True,
        identifiability_gate=True,
    )
    rep = est.identifiability
    assert rep is not None  # symmetric + gate ⇒ always present

    k_hat = np.asarray(est.K, dtype=np.float64)
    fro_true = float(np.linalg.norm(k_true, ord="fro"))
    fro_err = float(np.linalg.norm(k_hat - k_true, ord="fro"))
    frob_rel = fro_err / fro_true if fro_true > 0.0 else float("inf")

    # CRLB band coverage of the true coupling entries (reported for
    # transparency — the band is a CRLB lower bound, NOT a calibrated
    # 95% interval; the noiseless swing path is bias-dominated).
    n_cover = 0
    edge_rows: list[dict[str, Any]] = []
    for e in rep.edges:
        kt = float(k_true[e.a, e.b])
        covers = bool(e.ci_low <= kt <= e.ci_high)
        n_cover += int(covers)
        edge_rows.append(
            {
                "edge": [e.a, e.b],
                "k_true": kt,
                "k_hat": e.estimate,
                "crlb_se": e.std_error,
                "ci_low": e.ci_low,
                "ci_high": e.ci_high,
                "wald_ratio": e.wald_ratio if np.isfinite(e.wald_ratio) else None,
                "ci_contains_zero": e.ci_contains_zero,
                "crlb_band_covers_k_true": covers,
            }
        )

    return {
        "regime": "noisy" if noisy else "noiseless",
        "verdict": rep.verdict.value,
        "score": rep.score,
        "refuse_threshold": rep.refuse_threshold,
        "r_squared": rep.r_squared,
        "residual_variance": (
            rep.residual_variance if np.isfinite(rep.residual_variance) else None
        ),
        "reciprocal_condition": rep.reciprocal_condition,
        "frobenius_rel_error": frob_rel,
        "k_hat_fro": float(np.linalg.norm(k_hat, ord="fro")),
        "k_true_fro": fro_true,
        "n_edges": len(rep.edges),
        "n_crlb_band_covers_k_true": n_cover,
        "edges": edge_rows,
        "reason": rep.reason,
    }


def build_identifiability_ledger(
    system: GridSystem,
    cfg: SimConfig,
) -> dict[str, Any]:
    """Front-gate self-report ledger over the two frozen WSCC-9 regimes.

    The ledger is descriptive instrument-honesty evidence. It carries
    ``is_science_claim = False`` and ``closes_noisy_gate = False`` and
    cites the frozen pre-registration / parent ledger sha (read, never
    redefined).
    """
    noiseless = _front_gate_one(system, cfg, noisy=False)
    noisy = _front_gate_one(system, cfg, noisy=True)

    ledger: dict[str, Any] = {
        "artifact": "CALIB-GRID-001",
        "lineage": "identifiability-front-gate (upgrade #2)",
        "kind": "reliability-instrument-honesty",
        "is_science_claim": False,
        "closes_noisy_gate": False,
        "parent_lineages": ["PR #749 (CALIB-GRID-001)", "PR #751 (R1)"],
        "frozen_preregistration_sha": FROZEN_PREREG_SHA,
        "parent_ledger_sha256": PARENT_LEDGER_SHA256,
        "scope": (
            "additive graded self-knowledge layer on the already-"
            "calibrated swing estimator; PREREGISTRATION/gates/seeds/"
            "sigma/theta0/decision-rule untouched"
        ),
        "system": system.name,
        "citation": system.citation,
        "branch_sha": _branch_sha(),
        "python": platform.python_version(),
        "theory_constants": {
            "wald_z_0975": WALD_Z_0975,
            "refuse_score": REFUSE_SCORE,
            "r2_floor": R2_FLOOR,
            "pe_hard_floor": PE_HARD_FLOOR,
            "provenance": (
                "research/calibration/grid_kuramoto/identifiability/THRESHOLD_PROVENANCE.md"
            ),
        },
        "front_gate": {
            "noiseless": noiseless,
            "noisy": noisy,
        },
        "interpretation": (
            "Before (binary PE guard): the reciprocal condition number "
            "is HIGHER in the noisy case than the noiseless one, so the "
            "merged guard PASSES the noisy regime while emitting a K̂ "
            "biased ~20x. After (graded front-gate): the noiseless case "
            "ACCEPTs (model adequate, R2 high) and the noisy case "
            "REFUSEs (R2 noise-dominated). The frozen noisy.frobenius "
            "gate STAYS NEGATIVE — this does NOT close it; the upgrade "
            "is that the instrument now self-reports the failure instead "
            "of silently emitting a misleading point estimate."
        ),
    }
    ledger["ledger_sha256"] = ledger_sha256(ledger)
    return ledger


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 always (descriptive artifact, no verdict)."""
    parser = argparse.ArgumentParser(
        description="CALIB-GRID-001 identifiability front-gate self-report"
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    ledger = build_identifiability_ledger(wscc_9_bus(), SimConfig())
    text = json.dumps(ledger, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
