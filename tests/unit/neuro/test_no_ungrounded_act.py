# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The No-Ungrounded-Act apex invariant — one theorem above the whole system.

ADMISSIBLE iff H1 (homeostasis) ∧ H2 (arrow-of-time) ∧ H3 (synchrony) ∧ H4
(verification). These tests are defect-sensitive: dropping ANY single ground
forces FORBIDDEN, and H2 is proven by driving the REAL epistemic-audit budget
register (a within-run budget increase is a negative cost — an arrow-of-time
violation).
"""

from __future__ import annotations

import importlib.util
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "audit_no_ungrounded_act.py"
ARTIFACT = ROOT / "artifacts" / "inference" / "no_ungrounded_act.json"
SCHEMA = ROOT / "audit" / "schema" / "no_ungrounded_act.schema.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("nua", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nua = _load_tool()


def test_all_grounds_true_is_admissible() -> None:
    assert nua.act_admissible(h1=True, h2=True, h3=True, h4=True) == "ADMISSIBLE"


def test_any_single_missing_ground_is_forbidden() -> None:
    # Every configuration with at least one False ground must be FORBIDDEN.
    for h1, h2, h3, h4 in itertools.product([True, False], repeat=4):
        expected = "ADMISSIBLE" if (h1 and h2 and h3 and h4) else "FORBIDDEN"
        assert nua.act_admissible(h1=h1, h2=h2, h3=h3, h4=h4) == expected


def test_h2_budget_monotonicity_uses_real_audit() -> None:
    # The real epistemic-audit register on a monotone-non-increasing run holds.
    assert nua.budget_monotone_under_real_audit() is True


def test_h2_detects_arrow_of_time_violation() -> None:
    # A within-run budget INCREASE surfaces as a negative cost_paid — the real
    # register makes the arrow-of-time violation observable, not silent.
    from core.neuro.epistemic_audit import advance_entry
    from core.neuro.epistemic_validation import EpistemicPhase, EpistemicState

    def _s(seq: int, budget: float) -> EpistemicState:
        return EpistemicState(
            seq=seq,
            weight=1.0,
            budget=budget,
            invariant_floor=0.1,
            phase=EpistemicPhase.ACTIVE,
            state_hash=f"h{seq}",
            halt_reason=None,
        )

    increased = advance_entry(_s(0, 5.0), _s(1, 9.0))["cost_paid"]
    assert increased < 0.0  # arrow-of-time violation is visible


def test_build_apex_over_committed_artifacts_is_admissible() -> None:
    report = nua.build_apex(ROOT)
    assert report["gate"] == "ADMISSIBLE"
    assert report["verdict"] == "PASS"
    assert all(g["holds"] for g in report["grounds"])
    assert {g["id"] for g in report["grounds"]} == {"H1", "H2", "H3", "H4"}


def test_build_apex_forbidden_when_verification_absent(tmp_path) -> None:
    # No committed artifacts under an empty root -> H1/H3/H4 fail -> FORBIDDEN.
    report = nua.build_apex(tmp_path)
    assert report["gate"] == "FORBIDDEN"
    assert report["verdict"] == "FAIL"


def test_exit_code_enforces_forbidden() -> None:
    assert nua.exit_code({"verdict": "PASS"}, report_only=False) == 0
    assert nua.exit_code({"verdict": "FAIL"}, report_only=False) == 1
    assert nua.exit_code({"verdict": "FAIL"}, report_only=True) == 0


def test_committed_apex_artifact_is_schema_valid_and_admissible() -> None:
    report = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert report["schema"] == nua.SCHEMA_ID
    assert report["gate"] == "ADMISSIBLE" and report["verdict"] == "PASS"
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(report, json.loads(SCHEMA.read_text(encoding="utf-8")))
