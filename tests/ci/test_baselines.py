# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The FLAGSHIP-RQ-001 baseline-hierarchy gate must have teeth.

POSITIVE: a complete hierarchy with a fresh comparison report and a
prereg-consistent verdict -> the gate passes (exit 0).

NEGATIVE 1: a missing baseline tier -> the gate flags it (non-zero).
NEGATIVE 2: a report that claims SUPPORTED without meeting the preregistered
margin / reproducibility leg -> the gate flags the verdict mismatch.

The negative tests mutate an on-disk copy inside a temp dir (never the tracked
report) and restore nothing in the tree, so they can never leave it dirty.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINES_DIR = ROOT / "benchmarks" / "flagship_baselines"
for _p in (str(BASELINES_DIR), str(ROOT / "scripts" / "ci")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import baselines as B  # noqa: E402  (benchmarks/flagship_baselines/baselines.py)
import check_baselines as gate  # noqa: E402  (scripts/ci/check_baselines.py)


# --------------------------------------------------------------------------- #
# Baseline-definition invariants (each baseline is REAL, not a stub).           #
# --------------------------------------------------------------------------- #
def test_all_required_tiers_have_callable_definitions() -> None:
    """Complete hierarchy: every required tier maps to a real callable."""
    for tier in B.REQUIRED_TIERS:
        spec = B.BASELINES.get(tier)
        assert spec is not None, f"missing baseline tier: {tier}"
        assert callable(spec.fn), f"baseline tier {tier} is not callable (stub?)"


def test_baselines_are_runnable_and_return_sets() -> None:
    """Each baseline runs on the real snapshot-S context and returns a set."""
    ctx = B.EvidenceContext.from_artifact()
    for tier in B.REQUIRED_TIERS:
        caught = B.BASELINES[tier].fn(ctx)
        assert isinstance(caught, set), f"{tier} did not return a set"
    assert isinstance(B.flagship_check(ctx), set)


def test_flagship_beats_every_baseline_marginally() -> None:
    """The flagship catches defects NO baseline catches (marginal detection)."""
    ctx = B.EvidenceContext.from_artifact()
    flagship = B.flagship_check(ctx)
    existing = B.baseline_existing_suite(ctx)
    marginal = flagship - existing
    # On snapshot S the existing suite (and every other baseline) catches 0.
    assert B.baseline_naive(ctx) == set()
    assert len(marginal) >= B.PREREG_MARGIN, "flagship must clear the prereg margin"


def test_shuffled_null_control_catches_nothing() -> None:
    """Label-shuffle null: stdlib tokens are not first-party -> ~0 detections."""
    ctx = B.EvidenceContext.from_artifact()
    assert B.baseline_shuffled(ctx, seed=42) == set()
    # Determinism of the null.
    assert B.baseline_shuffled(ctx, seed=42) == B.baseline_shuffled(ctx, seed=42)


# --------------------------------------------------------------------------- #
# Decision rule (single source of truth).                                       #
# --------------------------------------------------------------------------- #
def test_decision_rule_rejects_on_zero_marginal() -> None:
    assert B.decide(0, reproducibility_verified=True, marginal_detection_confirmed=True) == "REJECTED"


def test_decision_rule_supported_requires_reproducibility() -> None:
    # Margin met + marginal confirmed but reproducibility NOT verified -> withheld.
    assert (
        B.decide(70, reproducibility_verified=False, marginal_detection_confirmed=True)
        == "INSUFFICIENT_EVIDENCE"
    )
    assert (
        B.decide(70, reproducibility_verified=True, marginal_detection_confirmed=True)
        == "SUPPORTED"
    )


# --------------------------------------------------------------------------- #
# POSITIVE: the tracked hierarchy + report pass the gate.                        #
# --------------------------------------------------------------------------- #
def test_gate_passes_on_complete_hierarchy() -> None:
    """Complete hierarchy + present comparison + prereg-consistent verdict."""
    verdict = gate.evaluate()
    assert verdict["ok"], f"gate should pass, got problems: {verdict['problems']}"
    assert gate.main([]) == 0


def test_committed_report_verdict_matches_prereg_rule() -> None:
    """The committed report's verdict equals a fresh re-derivation (no drift)."""
    report = json.loads(gate.COMPARISON_REPORT.read_text(encoding="utf-8"))
    rederived = B.decide(
        d_marginal=int(report["D_marginal"]),
        reproducibility_verified=bool(report["reproducibility_verified_at_S"]),
        marginal_detection_confirmed=bool(report["marginal_detection_confirmed"]),
        prereg_margin=int(report["prereg_margin"]),
    )
    assert rederived == report["verdict"]


# --------------------------------------------------------------------------- #
# NEGATIVE 1: a missing baseline tier -> gate non-zero.                          #
# --------------------------------------------------------------------------- #
def test_gate_fails_when_a_tier_is_missing(tmp_path, monkeypatch) -> None:
    """Drop EXISTING_SUITE from the report; the gate must flag the gap."""
    report = json.loads(gate.COMPARISON_REPORT.read_text(encoding="utf-8"))
    del report["baselines"]["EXISTING_SUITE"]
    broken = tmp_path / "comparison_report.json"
    broken.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(gate, "COMPARISON_REPORT", broken)

    verdict = gate.evaluate()
    assert not verdict["ok"]
    assert any("EXISTING_SUITE" in p for p in verdict["problems"])
    assert gate.main([]) == 1


# --------------------------------------------------------------------------- #
# NEGATIVE 2: a report claiming SUPPORTED without meeting the prereg margin.     #
# --------------------------------------------------------------------------- #
def test_gate_flags_unsupported_supported_claim(tmp_path, monkeypatch) -> None:
    """A tampered verdict 'SUPPORTED' with reproducibility unverified is caught."""
    report = json.loads(gate.COMPARISON_REPORT.read_text(encoding="utf-8"))
    # Keep the honest numbers (D_marginal>=1, reproducibility NOT verified) but
    # overwrite the verdict to the fabricated SUPPORTED. decide() would return
    # INSUFFICIENT_EVIDENCE, so the gate must flag the mismatch.
    report["verdict"] = "SUPPORTED"
    assert report["reproducibility_verified_at_S"] is False
    broken = tmp_path / "comparison_report.json"
    broken.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(gate, "COMPARISON_REPORT", broken)

    verdict = gate.evaluate()
    assert not verdict["ok"]
    assert any("does NOT match the preregistered rule" in p for p in verdict["problems"])
    assert gate.main([]) == 1


def test_gate_also_flags_supported_below_margin(tmp_path, monkeypatch) -> None:
    """Claiming SUPPORTED with D_marginal below the margin is likewise caught."""
    report = json.loads(gate.COMPARISON_REPORT.read_text(encoding="utf-8"))
    report["D_marginal"] = 0
    report["marginal_detection_confirmed"] = False
    report["reproducibility_verified_at_S"] = True
    report["verdict"] = "SUPPORTED"  # decide() -> REJECTED
    broken = tmp_path / "comparison_report.json"
    broken.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(gate, "COMPARISON_REPORT", broken)

    verdict = gate.evaluate()
    assert not verdict["ok"]
    assert gate.main([]) == 1
