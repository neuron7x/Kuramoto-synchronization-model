# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Phase 0 capsule schema contract test.

Required fields on every emission:
  * ``capsule_version == 'phase0_verification_capsule_v1'``
  * ``verdict ∈ {'PASS', 'FAIL'}``
  * ``sha256`` is a 64-char hex string
  * ``fallback_recommendation == 'M2'`` when verdict == 'FAIL'
  * Phase 0a/0b/0c per-cell evidence carried as ``cell_evidence`` list
"""

from __future__ import annotations

import re

from research.systemic_risk.d002g_phase0_capsule import (
    CAPSULE_VERSION,
    verdict_to_capsule,
)
from research.systemic_risk.d002g_phase0_verification import (
    Phase0aResult,
    Phase0bResult,
    Phase0CellEvidence,
    Phase0cResult,
    Phase0Verdict,
)


def _make_verdict(verdict_str: str) -> Phase0Verdict:
    cell = Phase0CellEvidence(
        substrate_id="ricci_flow",
        N=50,
        phase_0a=Phase0aResult(
            substrate_id="ricci_flow",
            N=50,
            passed=(verdict_str == "PASS"),
            array_equal=False,
            base_seed=42,
            null_seed=10042,
            detail="ok",
        ),
        phase_0b=Phase0bResult(
            substrate_id="ricci_flow",
            N=50,
            passed=(verdict_str == "PASS"),
            n_seeds=50,
            t_statistic=0.5,
            mean_diff=0.01,
            std_diff=0.5,
            threshold=2.0,
            detail="ok",
        ),
        phase_0c=Phase0cResult(
            substrate_id="ricci_flow",
            N=50,
            passed=(verdict_str == "PASS"),
            n_shuffles=1000,
            p_value_empirical=0.5,
            p_lo=0.05,
            p_hi=0.95,
            detail="ok",
        ),
        all_passed=(verdict_str == "PASS"),
    )
    return Phase0Verdict(
        verdict=verdict_str,
        cell_evidence=(cell,),
        fallback_recommendation=("M2" if verdict_str == "FAIL" else ""),
        metric_id="sync_auc",
        base_seed=42,
        null_seed_offset=10000,
        n_seeds=50,
        n_shuffles=1000,
        t_threshold=2.0,
        p_lo=0.05,
        p_hi=0.95,
    )


def test_capsule_contains_required_top_level_fields() -> None:
    v = _make_verdict("PASS")
    cap = verdict_to_capsule(v)
    for field in (
        "capsule_version",
        "verdict",
        "sha256",
        "cell_evidence",
        "fallback_recommendation",
        "metric_id",
        "base_seed",
        "null_seed_offset",
        "n_seeds",
        "n_shuffles",
        "t_threshold",
        "p_lo",
        "p_hi",
    ):
        assert field in cap, f"capsule missing required field {field!r}; got {sorted(cap)}"
    assert cap["capsule_version"] == CAPSULE_VERSION
    assert cap["verdict"] == "PASS"
    assert re.fullmatch(r"[0-9a-f]{64}", cap["sha256"])


def test_capsule_verdict_in_pass_or_fail() -> None:
    for verdict in ("PASS", "FAIL"):
        cap = verdict_to_capsule(_make_verdict(verdict))
        assert cap["verdict"] in {"PASS", "FAIL"}


def test_capsule_fail_recommends_M2() -> None:
    cap = verdict_to_capsule(_make_verdict("FAIL"))
    assert cap["fallback_recommendation"] == "M2", (
        f"Phase 0 FAIL must carry fallback_recommendation=='M2'; "
        f"got {cap['fallback_recommendation']!r}"
    )


def test_capsule_pass_has_empty_fallback() -> None:
    cap = verdict_to_capsule(_make_verdict("PASS"))
    assert cap["fallback_recommendation"] == ""


def test_capsule_per_cell_evidence_carries_three_phases() -> None:
    cap = verdict_to_capsule(_make_verdict("PASS"))
    cells = cap["cell_evidence"]
    assert len(cells) >= 1
    for cell in cells:
        assert "phase_0a" in cell
        assert "phase_0b" in cell
        assert "phase_0c" in cell
        assert "all_passed" in cell
