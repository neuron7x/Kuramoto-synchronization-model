# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Pre-registered acceptance gates for CALIB-GRID-001 (fail-closed).

The numeric gates below are the *single source of truth* and are copied
verbatim into ``PREREGISTRATION.md``; a test asserts the doc and this
module agree byte-for-numeric, so the verdict cannot drift post-data.

A miss is **informative**, not a failure of the artifact: each gate
carries the estimator stage it localises to, so a red gate points at
exactly the next refinement target. No promotion language is emitted on
partial success — the verdict is one of ``PASS`` / ``NEGATIVE``.
"""

from __future__ import annotations

from ._substrate import Gate as GateVerdict
from ._substrate import GateRow as GateResult
from .calibration import CalibrationMetrics

__all__ = [
    "GateResult",
    "GateVerdict",
    "NOISELESS_GATES",
    "NOISY_GATES",
    "evaluate_gates",
    "overall_verdict",
]


# --- Pre-registered, frozen. Mirror of PREREGISTRATION.md § 4. ---------------

NOISELESS_GATES: tuple[GateVerdict, ...] = (
    GateVerdict(
        name="noiseless.frobenius",
        metric_key="frobenius_rel_error",
        operator="<=",
        threshold=0.10,
        localises_to="coupling_estimator row-regression bias / λ_reg",
    ),
    GateVerdict(
        name="noiseless.topology_f1",
        metric_key="topology_f1",
        operator=">=",
        threshold=0.95,
        localises_to="coupling_estimator sparse-support thresholding",
    ),
    GateVerdict(
        name="noiseless.critical_coupling",
        metric_key="critical_coupling_rel_error",
        operator="<=",
        threshold=0.15,
        localises_to="end-to-end (K_hat propagated through Dörfler–Bullo)",
    ),
)

NOISY_GATES: tuple[GateVerdict, ...] = (
    GateVerdict(
        name="noisy.frobenius",
        metric_key="frobenius_rel_error",
        operator="<=",
        threshold=0.25,
        localises_to="coupling_estimator noise robustness / standardisation",
    ),
    GateVerdict(
        name="noisy.topology_f1",
        metric_key="topology_f1",
        operator=">=",
        threshold=0.90,
        localises_to="coupling_estimator support stability under σ",
    ),
)


def evaluate_gates(
    metrics: CalibrationMetrics,
    gates: tuple[GateVerdict, ...],
) -> list[GateResult]:
    """Evaluate every gate against ``metrics`` (no thresholds re-defined)."""
    payload = metrics.to_dict()
    out: list[GateResult] = []
    for gate in gates:
        observed = float(payload[gate.metric_key])
        out.append(
            GateResult(
                name=gate.name,
                metric_key=gate.metric_key,
                observed=observed,
                operator=gate.operator,
                threshold=gate.threshold,
                passed=gate.check(observed),
                localises_to=gate.localises_to,
            )
        )
    return out


def overall_verdict(results: list[GateResult]) -> str:
    """``"PASS"`` iff every gate passed, else ``"NEGATIVE"`` (fail-closed)."""
    return "PASS" if all(r.passed for r in results) else "NEGATIVE"
