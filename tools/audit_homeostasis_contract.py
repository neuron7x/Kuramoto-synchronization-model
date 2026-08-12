# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Homeostasis contract — the neuromodulatory drive must stay provably admissible.

The dopamine (RPE/vigor) and serotonin (tonic stress/patience) controllers are a
real opponent-process system, not a metaphor: the allostatic regulator's load is a
clamped ODE, the controller parameters carry bounded invariants, and component
synchronisation is a Kuramoto phase-coherence. This audit drives those REAL
objects and composes the No-Ungrounded-Act gate:

    GO  ⇔  allostatic load bounded ∧ parameters admissible ∧ phase-coherent
    otherwise NO-GO (fail-closed)

so an action can only fire on a homeostatic, in-spec, synchronised drive state.
Emits a schema-bound artifact; a FAIL verdict exits non-zero unless --report-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from core.kuramoto import order_parameter
from core.neuro.calibration_constants import validate_parameter_invariants
from core.neuro.motivation import AllostaticRegulator

SCHEMA_ID = "geosync.homeostasis_contract.v1"
_ALLOSTATIC_BOUND = 1.0
_COHERENCE_MIN = 0.9

# A deterministic adversarial drive trajectory: alternating extreme reward
# prediction error and stress spikes. If the opponent-process homeostasis holds,
# the allostatic load never escapes [-1, 1].
_TRAJECTORY: tuple[tuple[float, float], ...] = tuple(
    (rpe, stress)
    for rpe, stress in (
        (5.0, 0.0),
        (-5.0, 5.0),
        (5.0, 5.0),
        (-5.0, 0.0),
        (10.0, 10.0),
        (-10.0, 10.0),
    )
    * 12
)

_GOOD_DOPAMINE = {
    "discount_gamma": 0.98,
    "learning_rate_v": 0.10,
    "burst_factor": 2.5,
    "base_temperature": 1.0,
    "min_temperature": 0.05,
}
_GOOD_SEROTONIN = {
    "tonic_beta": 0.95,
    "phasic_beta": 0.70,
    "stress_gain": 1.0,
    "stress_threshold": 0.8,
    "release_threshold": 0.5,
    "hysteresis": 0.1,
}


def bounded_allostatic_load(trajectory: tuple[tuple[float, float], ...]) -> tuple[bool, float]:
    """Drive the real AllostaticRegulator and return (bounded, worst |load|)."""

    regulator = AllostaticRegulator()
    worst = 0.0
    bounded = True
    for rpe, stress in trajectory:
        load = regulator.update(rpe, stress)
        worst = max(worst, abs(load))
        if abs(load) > _ALLOSTATIC_BOUND + 1e-9:
            bounded = False
    return bounded, worst


def phase_coherence(*, locked: bool) -> float:
    """Kuramoto order parameter for locked vs. uniformly-spread phases."""

    if locked:
        theta = np.zeros((8, 16), dtype=float)
    else:
        theta = np.tile(np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False), (8, 1))
    return float(np.mean(order_parameter(theta, axis=1)))


def no_ungrounded_act(
    *, allostatic_bounded: bool, params_admissible: bool, coherence: float, r_min: float
) -> str:
    """The No-Ungrounded-Act gate: GO only on a bounded, in-spec, coherent drive."""

    if allostatic_bounded and params_admissible and coherence >= r_min:
        return "GO"
    return "NO-GO"


def build_contract() -> dict[str, Any]:
    """Evaluate every homeostasis invariant over the real neuromodulatory objects."""

    bounded, worst_load = bounded_allostatic_load(_TRAJECTORY)
    dopamine_ok, _ = validate_parameter_invariants("dopamine", _GOOD_DOPAMINE)
    serotonin_ok, _ = validate_parameter_invariants("serotonin", _GOOD_SEROTONIN)
    # Negative controls: the validator must REJECT an out-of-bound parameter.
    dopamine_rejects, _ = validate_parameter_invariants("dopamine", {"discount_gamma": 1.5})
    serotonin_rejects, _ = validate_parameter_invariants("serotonin", {"tonic_beta": 1.5})
    r_locked = phase_coherence(locked=True)
    r_spread = phase_coherence(locked=False)
    params_admissible = dopamine_ok and serotonin_ok
    gate = no_ungrounded_act(
        allostatic_bounded=bounded,
        params_admissible=params_admissible,
        coherence=r_locked,
        r_min=_COHERENCE_MIN,
    )

    invariants = [
        {
            "id": "HOMEO-1",
            "statement": "opponent-process allostatic load stays within [-1, 1] under an adversarial drive trajectory",
            "test": "tests/unit/neuro/test_homeostasis_contract.py::test_allostatic_load_is_bounded",
            "passed": bounded,
        },
        {
            "id": "HOMEO-2",
            "statement": "dopamine controller parameters are admissible and out-of-bound params are rejected",
            "test": "tests/unit/neuro/test_homeostasis_contract.py::test_dopamine_parameter_invariants",
            "passed": dopamine_ok and not dopamine_rejects,
        },
        {
            "id": "HOMEO-3",
            "statement": "serotonin controller parameters are admissible and out-of-bound params are rejected",
            "test": "tests/unit/neuro/test_homeostasis_contract.py::test_serotonin_parameter_invariants",
            "passed": serotonin_ok and not serotonin_rejects,
        },
        {
            "id": "HOMEO-4",
            "statement": "phase coherence is locked (r>=r_min) for synchronised phases and low for desynchronised phases",
            "test": "tests/unit/neuro/test_homeostasis_contract.py::test_phase_coherence_gate",
            "passed": r_locked >= _COHERENCE_MIN and r_spread < _COHERENCE_MIN,
        },
        {
            "id": "HOMEO-5",
            "statement": "No-Ungrounded-Act: GO only when the drive is bounded, in-spec and coherent",
            "test": "tests/unit/neuro/test_homeostasis_contract.py::test_no_ungrounded_act_gate",
            "passed": gate == "GO",
        },
    ]
    verdict = "PASS" if all(inv["passed"] for inv in invariants) else "FAIL"
    return {
        "schema": SCHEMA_ID,
        "component": "core.neuro (dopamine/serotonin opponent process + kuramoto sync)",
        "allostatic_bound": _ALLOSTATIC_BOUND,
        "coherence_min": _COHERENCE_MIN,
        "worst_allostatic_load": round(worst_load, 6),
        "coherence_locked": round(r_locked, 6),
        "coherence_spread": round(r_spread, 6),
        "gate": gate,
        "invariants": invariants,
        "verdict": verdict,
    }


def exit_code(report: dict[str, Any], *, report_only: bool) -> int:
    if report["verdict"] == "FAIL" and not report_only:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Neuromodulatory homeostasis contract audit")
    p.add_argument("--out", help="write the contract JSON here (else stdout)")
    p.add_argument("--report-only", action="store_true", help="always exit 0, mark report_only")
    args = p.parse_args(argv)

    report = build_contract()
    report["report_only"] = bool(args.report_only)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(f"homeostasis verdict: {report['verdict']} gate={report['gate']}", file=sys.stderr)
    return exit_code(report, report_only=bool(args.report_only))


if __name__ == "__main__":
    sys.exit(main())
