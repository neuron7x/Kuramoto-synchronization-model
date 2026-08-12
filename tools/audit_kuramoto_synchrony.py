# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""N6 — synchronisation certificate for the Kuramoto engine (second domain).

This is a TRANSFER: the same apparatus that certified the neuromodulatory drive
(artifact → schema → falsifier → CI gate → fail-closed verdict) applied to a
mathematically distinct object — the Kuramoto phase oscillators. It certifies the
real engine exhibits the synchronisation phase transition:

    strong coupling  → order parameter locks   (r_steady >= r_lock)
    weak coupling    → incoherence             (r_steady <  r_incoherent)
    a phase transition exists                   (r_high - r_low >= gap)
    r ∈ [0, 1] always                           (order-parameter invariant)
    same seed → same trajectory                 (determinism)

grounded in the real KuramotoEngine. A non-synchronising verdict exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from core.kuramoto import KuramotoConfig, KuramotoEngine

SCHEMA_ID = "geosync.kuramoto_synchrony.v1"
_R_LOCK = 0.9
_R_INCOHERENT = 0.5
_TRANSITION_GAP = 0.5
_SEED = 7
_N = 24


def r_steady(coupling: float, *, seed: int = _SEED) -> float:
    """Mean order parameter over the tail of a real Kuramoto run (deterministic)."""

    config = KuramotoConfig(N=_N, K=coupling, dt=0.05, steps=600, seed=seed)
    result = KuramotoEngine(config).run()
    order = np.asarray(result.order_parameter, dtype=float)
    return float(order[-200:].mean())


def order_parameter_bounded(coupling: float) -> bool:
    """The order parameter r = |mean(e^{iθ})| must stay in [0, 1] at every step."""

    config = KuramotoConfig(N=_N, K=coupling, dt=0.05, steps=300, seed=_SEED)
    order = np.asarray(KuramotoEngine(config).run().order_parameter, dtype=float)
    return bool(np.all(order >= -1e-9) and np.all(order <= 1.0 + 1e-9))


def build_certificate() -> dict[str, Any]:
    """Evaluate the synchronisation phase-transition checks on the real engine."""

    r_high = r_steady(5.0)
    r_mid = r_steady(1.0)
    r_low = r_steady(0.05)
    locks = r_high >= _R_LOCK
    incoherent = r_low < _R_INCOHERENT
    # A phase transition exists: the locked regime is separated from the incoherent
    # one by a clear gap. (Fine-grained monotonicity is not asserted — near/below
    # the critical coupling the order parameter is a finite-size-noisy plateau.)
    transition = (r_high - r_low) >= _TRANSITION_GAP
    bounded = order_parameter_bounded(5.0)
    deterministic = abs(r_steady(1.0) - r_steady(1.0)) < 1e-12

    checks = [
        {
            "id": "KURA-1",
            "name": "strong coupling locks (r_steady >= r_lock)",
            "holds": bool(locks),
        },
        {
            "id": "KURA-2",
            "name": "weak coupling is incoherent (r_steady < r_incoherent)",
            "holds": bool(incoherent),
        },
        {
            "id": "KURA-3",
            "name": "a synchronisation phase transition exists (r_high - r_low >= gap)",
            "holds": bool(transition),
        },
        {"id": "KURA-4", "name": "order parameter stays in [0, 1]", "holds": bool(bounded)},
        {
            "id": "KURA-5",
            "name": "same seed reproduces the same trajectory",
            "holds": bool(deterministic),
        },
    ]
    verdict = "SYNCHRONISING" if all(c["holds"] for c in checks) else "INCOHERENT"
    return {
        "schema": SCHEMA_ID,
        "component": "core.kuramoto.KuramotoEngine (phase oscillators)",
        "r_lock": _R_LOCK,
        "r_steady_high": round(r_high, 6),
        "r_steady_mid": round(r_mid, 6),
        "r_steady_low": round(r_low, 6),
        "checks": checks,
        "gate": verdict,
        "verdict": "PASS" if verdict == "SYNCHRONISING" else "FAIL",
    }


def exit_code(report: dict[str, Any], *, report_only: bool) -> int:
    if report["verdict"] == "FAIL" and not report_only:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Kuramoto synchronisation certificate")
    p.add_argument("--out", help="write the certificate JSON here (else stdout)")
    p.add_argument("--report-only", action="store_true", help="always exit 0, mark report_only")
    args = p.parse_args(argv)

    report = build_certificate()
    report["report_only"] = bool(args.report_only)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(f"kuramoto synchrony: {report['gate']}", file=sys.stderr)
    return exit_code(report, report_only=bool(args.report_only))


if __name__ == "__main__":
    sys.exit(main())
