# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Neuromodulatory homeostasis contract — drives the REAL controllers.

The dopamine/serotonin opponent process is not a metaphor: these tests exercise
the real AllostaticRegulator ODE, the real parameter-invariant validator, and the
real Kuramoto order parameter. They are defect-sensitive — remove the allostatic
clamp, loosen a bound, or wire the gate to ignore coherence, and a test fails.
The contract binds them into the No-Ungrounded-Act gate: GO only on a bounded,
in-spec, phase-coherent drive.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "audit_homeostasis_contract.py"
ARTIFACT = ROOT / "artifacts" / "neuro" / "homeostasis_contract.json"
SCHEMA = ROOT / "audit" / "schema" / "homeostasis_contract.schema.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("homeo", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hc = _load_tool()


# HOMEO-1
def test_allostatic_load_is_bounded() -> None:
    bounded, worst = hc.bounded_allostatic_load(hc._TRAJECTORY)
    assert bounded is True
    assert worst <= hc._ALLOSTATIC_BOUND + 1e-9


# HOMEO-2
def test_dopamine_parameter_invariants() -> None:
    from core.neuro.calibration_constants import validate_parameter_invariants

    ok, _ = validate_parameter_invariants("dopamine", hc._GOOD_DOPAMINE)
    assert ok is True
    # Negative control: an out-of-bound discount factor must be rejected.
    rejected, errors = validate_parameter_invariants("dopamine", {"discount_gamma": 1.5})
    assert rejected is False and errors


# HOMEO-3
def test_serotonin_parameter_invariants() -> None:
    from core.neuro.calibration_constants import validate_parameter_invariants

    ok, _ = validate_parameter_invariants("serotonin", hc._GOOD_SEROTONIN)
    assert ok is True
    rejected, errors = validate_parameter_invariants("serotonin", {"tonic_beta": 1.5})
    assert rejected is False and errors


# HOMEO-4
def test_phase_coherence_gate() -> None:
    r_locked = hc.phase_coherence(locked=True)
    r_spread = hc.phase_coherence(locked=False)
    assert r_locked >= hc._COHERENCE_MIN  # synchronised phases lock
    assert r_spread < hc._COHERENCE_MIN  # spread phases do not
    assert 0.0 <= r_spread <= 1.0 and 0.0 <= r_locked <= 1.0


# HOMEO-5
def test_no_ungrounded_act_gate() -> None:
    assert (
        hc.no_ungrounded_act(
            allostatic_bounded=True, params_admissible=True, coherence=1.0, r_min=0.9
        )
        == "GO"
    )
    # Any single failing precondition forces NO-GO (fail-closed).
    assert (
        hc.no_ungrounded_act(
            allostatic_bounded=False, params_admissible=True, coherence=1.0, r_min=0.9
        )
        == "NO-GO"
    )
    assert (
        hc.no_ungrounded_act(
            allostatic_bounded=True, params_admissible=False, coherence=1.0, r_min=0.9
        )
        == "NO-GO"
    )
    assert (
        hc.no_ungrounded_act(
            allostatic_bounded=True, params_admissible=True, coherence=0.5, r_min=0.9
        )
        == "NO-GO"
    )


def test_contract_build_is_pass_and_go() -> None:
    report = hc.build_contract()
    assert report["verdict"] == "PASS"
    assert report["gate"] == "GO"
    assert all(inv["passed"] for inv in report["invariants"])


def test_exit_code_enforces_fail() -> None:
    assert hc.exit_code({"verdict": "PASS"}, report_only=False) == 0
    assert hc.exit_code({"verdict": "FAIL"}, report_only=False) == 1
    assert hc.exit_code({"verdict": "FAIL"}, report_only=True) == 0


def test_committed_artifact_matches_schema_and_tests() -> None:
    report = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert report["schema"] == hc.SCHEMA_ID
    assert report["verdict"] == "PASS"
    for inv in report["invariants"]:
        node = inv["test"]
        file_part, _, func = node.partition("::")
        path = ROOT / file_part
        assert path.is_file(), f"missing test file: {file_part}"
        assert f"def {func}" in path.read_text(encoding="utf-8"), func
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(report, json.loads(SCHEMA.read_text(encoding="utf-8")))
