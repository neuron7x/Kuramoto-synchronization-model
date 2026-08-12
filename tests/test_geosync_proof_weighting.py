# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth for the epistemic-integrity weighting layer.

Each test states, in its assertion message, the failure it would catch -- a test
that cannot fail is worthless, so every case here has a matched control that
distinguishes it from its neighbour (toothless != proven != unmeasured; a REFUTED
P0 != any pile of green claims).
"""

from __future__ import annotations

import pytest

from geosync.proof.weighting import (
    ModuleRecord,
    UNMEASURED_SCALAR_FLOOR,
    build_report,
    calibrated_support,
    claim_contribution,
    falsification_power,
    integrity_score,
    records_from_manifests,
    score_views,
)


# ---------------------------------------------------------------------------
# Fixtures: hand-built records + claim views (no source is ever mutated here).
# ---------------------------------------------------------------------------
def _rec(module, killed, total, tests=(), manifest="test"):
    return ModuleRecord(module=module, killed=killed, total=total, tests=tuple(tests), manifest=manifest)


def _view(cid, verdict, *, priority="P0", tier="ANCHORED", test_id=None, evidence=()):
    return {
        "id": cid,
        "priority": priority,
        "tier": tier,
        "verdict": verdict,
        "test_id": test_id,
        "evidence_paths": list(evidence),
    }


# Modules with DIFFERENT demonstrated teeth, matched by source path.
PROVEN = _rec("core/proven.py", killed=12, total=12)      # kills every mutant -> 1.0
TOOTHLESS = _rec("core/toothless.py", killed=0, total=8)  # ran, killed none  -> 0.0
PARTIAL = _rec("core/partial.py", killed=16, total=21)    # 0.7619...
EMPTY = _rec("core/empty.py", killed=0, total=0)          # zero valid mutants -> UNMEASURED
RECORDS = [PROVEN, TOOTHLESS, PARTIAL, EMPTY]


# ===========================================================================
# 1. falsification_power: the UNMEASURED sentinel is NOT 1.0 (the fail-open trap)
# ===========================================================================
def test_unmeasured_power_is_sentinel_not_one():
    """A claim with no recorded mutation evidence must be UNMEASURED, and its
    forced scalar must be 0.0 -- NEVER 1.0 (mutation_probe.Report.kill_rate's
    total==0 -> 1.0 default is the exact trap this layer must not inherit)."""
    p = falsification_power(_view("c", "SUPPORTED", evidence=["core/not_recorded.py"]), RECORDS)
    assert p.state == "UNMEASURED", "no recorded evidence must yield the UNMEASURED sentinel"
    assert p.value is None, "UNMEASURED must carry None, not a number"
    assert p.scalar() == UNMEASURED_SCALAR_FLOOR == 0.0
    assert p.scalar() != 1.0, "REGRESSION to the fail-open total==0 -> 1.0 trap"


def test_zero_valid_mutants_is_unmeasured_not_perfect():
    """A record that ran but produced ZERO valid mutants demonstrates no teeth;
    it must be UNMEASURED, not a perfect 1.0."""
    p = falsification_power(_view("c", "SUPPORTED", evidence=["core/empty.py"]), RECORDS)
    assert p.state == "UNMEASURED" and p.reason == "zero_mutants"
    assert p.scalar() == 0.0 and p.scalar() != 1.0


# ===========================================================================
# 2. A toothless-but-passing SUPPORTED weights ~0; a mutation-proven one ~full.
# ===========================================================================
def test_toothless_supported_earns_zero():
    """SUPPORTED whose falsifier was MEASURED to kill nothing must earn 0.0 --
    a passing test that cannot fail is worthless (Karpathy)."""
    p = falsification_power(_view("c", "SUPPORTED", evidence=["core/toothless.py"]), RECORDS)
    assert p.measured and p.value == 0.0, "killed=0/total=8 is a MEASURED zero"
    assert calibrated_support("SUPPORTED", p) == 0.0
    assert claim_contribution("SUPPORTED", p) == 0.0


def test_proven_supported_earns_full():
    """SUPPORTED whose falsifier kills every injected mutant earns full weight."""
    p = falsification_power(_view("c", "SUPPORTED", evidence=["core/proven.py"]), RECORDS)
    assert p.measured and p.value == 1.0 and p.n_mutants == 12
    assert calibrated_support("SUPPORTED", p) == 1.0
    assert claim_contribution("SUPPORTED", p) == 1.0


def test_proven_strictly_beats_toothless():
    """POSITIVE CONTROL: the measure must actually DISTINGUISH a proven falsifier
    from a toothless one -- if these ever score equal, the layer is inert."""
    proven = falsification_power(_view("a", "SUPPORTED", evidence=["core/proven.py"]), RECORDS)
    toothless = falsification_power(_view("b", "SUPPORTED", evidence=["core/toothless.py"]), RECORDS)
    assert proven.scalar() > toothless.scalar(), "calibration is inert: proven == toothless"

    e_proven = integrity_score(score_views([_view("a", "SUPPORTED", evidence=["core/proven.py"])], RECORDS))
    e_toothless = integrity_score(score_views([_view("b", "SUPPORTED", evidence=["core/toothless.py"])], RECORDS))
    assert e_proven["value"] > e_toothless["value"]
    assert e_proven["value"] == pytest.approx(1.0)   # (1+1)/2
    assert e_toothless["value"] == pytest.approx(0.5)  # (0+1)/2 -- neutral, NOT a pass


def test_partial_kill_rate_flows_through():
    """A partial recorded kill-rate (16/21) must flow through verbatim -- no
    rounding to 0 or 1, no invented constant."""
    p = falsification_power(_view("c", "SUPPORTED", evidence=["core/partial.py"]), RECORDS)
    assert p.value == pytest.approx(16 / 21)
    assert claim_contribution("SUPPORTED", p) == pytest.approx(16 / 21)


# ===========================================================================
# 3. A REFUTED P0 forces REJECT regardless of any pile of green claims.
# ===========================================================================
def test_refuted_p0_forces_reject_gate_zero():
    """One REFUTED P0 among many proven-SUPPORTED claims must drive the reject
    gate to 0 and E to 0.0 -- weakest-link dominates; greens cannot mask it."""
    views = [_view(f"green{i}", "SUPPORTED", priority="P2", evidence=["core/proven.py"]) for i in range(20)]
    views.append(_view("bad", "REFUTED", priority="P0"))
    e = integrity_score(score_views(views, RECORDS))
    assert e["reject_gate"] == 0, "a REFUTED claim must down the reject gate"
    assert e["value"] == 0.0, "E must collapse to 0 regardless of 20 green P2 claims"
    assert "bad" in e["reject_class_ids"]


def test_greens_without_reject_do_not_collapse():
    """CONTROL for the gate: the SAME 20 greens WITHOUT the REFUTED claim must
    NOT collapse -- proving the collapse above is caused by the REFUTED, not by
    the gate always firing."""
    views = [_view(f"green{i}", "SUPPORTED", priority="P2", evidence=["core/proven.py"]) for i in range(20)]
    e = integrity_score(score_views(views, RECORDS))
    assert e["reject_gate"] == 1
    assert e["value"] == pytest.approx(1.0)


@pytest.mark.parametrize("bad_verdict", ["REFUTED", "DANGLING", "FORBIDDEN_LANGUAGE"])
def test_all_reject_class_verdicts_gate(bad_verdict):
    """Every audit REJECT-class verdict (not just REFUTED) forces the gate down
    and contributes g = -1."""
    e = integrity_score(score_views([_view("x", bad_verdict, priority="P0")], RECORDS))
    assert e["reject_gate"] == 0 and e["value"] == 0.0


# ===========================================================================
# 4. Calibration coverage is co-reported and honest.
# ===========================================================================
def test_calibration_coverage_counts_only_measured_supporteds():
    views = [
        _view("proven", "SUPPORTED", evidence=["core/proven.py"]),        # measured
        _view("toothless", "SUPPORTED", evidence=["core/toothless.py"]),  # measured (zero)
        _view("blind", "SUPPORTED", evidence=["core/not_recorded.py"]),   # UNMEASURED
    ]
    e = integrity_score(score_views(views, RECORDS))
    assert e["supported_total"] == 3
    assert e["supported_calibrated"] == 2  # measured-zero still counts as measured
    assert e["calibration_coverage"] == pytest.approx(2 / 3)
    assert e["tier"] == "EXTRAPOLATED", "coverage < 1.0 must keep E EXTRAPOLATED"


def test_full_coverage_anchors_tier():
    views = [_view("proven", "SUPPORTED", evidence=["core/proven.py"])]
    e = integrity_score(score_views(views, RECORDS))
    assert e["calibration_coverage"] == 1.0 and e["tier"] == "ANCHORED"


def test_no_supported_coverage_is_none():
    """With no SUPPORTED claim, coverage is undefined (None) and E is not
    ANCHORED -- E has nothing verified to stand on."""
    e = integrity_score(score_views([_view("x", "NOT_TESTED")], RECORDS))
    assert e["calibration_coverage"] is None and e["tier"] == "EXTRAPOLATED"


# ===========================================================================
# 5. The tests-field join key works (falsifier node inside a recorded test file).
# ===========================================================================
def test_join_via_tests_field():
    """A claim whose falsifier node lives in a record's declared test file joins
    even when evidence_paths names no recorded source module."""
    rec = _rec("core/second_order.py", 16, 21, tests=("tests/unit/physics/test_second_order.py",))
    view = _view(
        "c",
        "SUPPORTED",
        test_id="tests/unit/physics/test_second_order.py::test_energy",
        evidence=[],
    )
    p = falsification_power(view, [rec])
    assert p.measured and p.value == pytest.approx(16 / 21)
    assert p.matched_modules == ("core/second_order.py",)


# ===========================================================================
# 6. Manifest normalisation: valid_mutants -> total; disjoint modules pool.
# ===========================================================================
def test_records_from_manifests_normalises_both_shapes():
    baseline = {"modules": {"core/a.py": {"killed": 3, "total": 3, "tests": "tests/test_a.py"}}}
    modules = {"per_module": {"modules/b.py": {"killed": 6, "valid_mutants": 24, "tests": "tests/test_b.py"}}}
    recs = records_from_manifests(baseline, modules)
    by_mod = {r.module: r for r in recs}
    assert by_mod["core/a.py"].total == 3 and by_mod["core/a.py"].killed == 3
    assert by_mod["modules/b.py"].total == 24 and by_mod["modules/b.py"].killed == 6


# ===========================================================================
# 7. End-to-end on the REAL committed artifacts: the honest negative, and
#    tamper-evidence.
# ===========================================================================
def test_real_artifacts_report_is_self_consistent():
    """The file-bound report over the committed artifacts must build, expose a
    reject gate, calibration coverage, and a recomputable content digest."""
    import pytest
    from geosync.proof.weighting import AUDIT_JSON
    if not AUDIT_JSON.exists():
        pytest.skip("no executed audit.json present; run `python -m geosync.proof.audit` first")
    from geosync.proof.run import DIGEST_KEY, _content_digest

    report = build_report()
    e = report["epistemic_integrity"]
    assert set(e).issuperset({"value", "reject_gate", "calibration_coverage", "tier", "scope"})
    # tamper-evidence: the digest recomputes over the report minus itself.
    body = {k: v for k, v in report.items() if k != DIGEST_KEY}
    assert report[DIGEST_KEY] == _content_digest(body)
    # honest coverage: if there are zero calibrated SUPPORTEDs, E must not be ANCHORED.
    if e["supported_calibrated"] == 0:
        assert e["tier"] == "EXTRAPOLATED"


def test_determinism_same_inputs_same_report():
    """Pure/deterministic: two builds over identical inputs are byte-identical
    (aside from the timestamp, pinned by SOURCE_DATE_EPOCH in the harness)."""
    import pytest
    from geosync.proof.weighting import AUDIT_JSON
    if not AUDIT_JSON.exists():
        pytest.skip("no executed audit.json present; run `python -m geosync.proof.audit` first")
    import os

    os.environ["SOURCE_DATE_EPOCH"] = "1700000000"
    a = build_report()
    b = build_report()
    assert a == b