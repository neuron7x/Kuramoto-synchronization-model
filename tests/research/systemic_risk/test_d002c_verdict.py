# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.5 — Verdict derivation tests."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import pytest

from research.systemic_risk.d002c_preregistration import (
    D002CPreregistration,
    load_and_lock,
)
from research.systemic_risk.d002c_sweep_runner import (
    SweepCellOutput,
    SweepResult,
)
from research.systemic_risk.d002c_verdict import (
    FPR_MAX,
    MARGIN_RELATIVE,
    SIGNAL_CI_RATIO_MIN,
    TIER_FAIL,
    TIER_PASS,
    VerdictInvalid,
    VerdictResult,
    derive_verdict,
)

CANONICAL_YAML = (
    Path(__file__).resolve().parents[3] / "docs" / "governance" / "D002C_PREREGISTRATION.yaml"
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _cell(
    *,
    cell_key: str,
    substrate_id: str = "block_structured",
    metric_id: str = "sync_auc",
    N: int = 100,
    lambda_: float = 0.40,
    signal_mean: float = 0.5,
    bca_ci_lo: float = 0.0,
    bca_ci_hi: float = 0.4,
    signal_over_ci: float = 2.5,
    direction: str = "up",
) -> SweepCellOutput:
    return SweepCellOutput(
        cell_key=cell_key,
        substrate_id=substrate_id,
        metric_id=metric_id,
        N=N,
        lambda_=lambda_,
        n_seeds=20,
        n_bootstrap=16,
        signal_mean=signal_mean,
        bca_ci_lo=bca_ci_lo,
        bca_ci_hi=bca_ci_hi,
        signal_over_ci=signal_over_ci,
        direction=direction,
        censoring_fraction_precursor=0.0,
        censoring_fraction_null=0.0,
        wallclock_seconds=1.0,
        sha256="a" * 64,
    )


def _sweep(
    cells: tuple[SweepCellOutput, ...],
    *,
    preregistration_sha: str = "deadbeef" + "00" * 28,
) -> SweepResult:
    return SweepResult(
        preregistration_sha=preregistration_sha,
        completed_cells=len(cells),
        total_cells=len(cells),
        results=cells,
        sha256="b" * 64,
        generated_at="2026-05-12T00:00:00Z",
        wallclock_seconds=10.0,
    )


def _prereg() -> D002CPreregistration:
    """Real prereg loaded from canonical YAML — the sha is what
    derive_verdict cross-checks against the sweep_result."""
    return load_and_lock(CANONICAL_YAML)


def _sweep_with_real_prereg(cells: tuple[SweepCellOutput, ...]) -> SweepResult:
    return _sweep(cells, preregistration_sha=_prereg().preregistration_sha)


# ---------------------------------------------------------------------------
# TIER_PASS path
# ---------------------------------------------------------------------------


def test_tier_pass_when_single_strong_cell_passes_all_three_rules() -> None:
    pre_cell = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        signal_over_ci=3.0,
        direction="up",
    )
    null_cell = _cell(
        cell_key='[100,0,"block_structured","sync_auc"]',
        lambda_=0.0,
        signal_over_ci=0.2,
        direction="none",
    )
    sweep = _sweep_with_real_prereg((pre_cell, null_cell))
    v = derive_verdict(sweep, _prereg())
    assert v.tier == TIER_PASS
    assert v.selected_cell_key == pre_cell.cell_key
    assert v.n_passing_cells == 1
    assert v.preregistration_sha == _prereg().preregistration_sha


def test_tier_pass_carries_canonical_sha256() -> None:
    pre_cell = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        signal_over_ci=3.0,
    )
    null_cell = _cell(
        cell_key='[100,0,"block_structured","sync_auc"]',
        lambda_=0.0,
        signal_over_ci=0.1,
        direction="none",
    )
    sweep = _sweep_with_real_prereg((pre_cell, null_cell))
    v = derive_verdict(sweep, _prereg())
    assert len(v.sha256) == 64
    assert all(c in "0123456789abcdef" for c in v.sha256)


# ---------------------------------------------------------------------------
# TIER_FAIL paths
# ---------------------------------------------------------------------------


def test_tier_fail_when_no_cell_passes_R1() -> None:
    cells = (
        _cell(
            cell_key='[100,0.4,"block_structured","sync_auc"]',
            signal_over_ci=0.5,
        ),
        _cell(
            cell_key='[100,0,"block_structured","sync_auc"]',
            lambda_=0.0,
            signal_over_ci=0.1,
            direction="none",
        ),
    )
    sweep = _sweep_with_real_prereg(cells)
    v = derive_verdict(sweep, _prereg())
    assert v.tier == TIER_FAIL
    assert v.selected_cell_key is None
    assert v.n_passing_cells == 0


def test_tier_fail_when_R2_breaks_via_excessive_fpr() -> None:
    """A high-signal precursor cell still fails if many null cells
    (lambda=0) exhibit signal_over_ci > 1 — that's an FPR > 0.05."""
    pre = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        signal_over_ci=5.0,
    )
    # 20 null cells — 5 of them exhibit FP signal → FPR = 0.25 > 0.05
    nulls = tuple(
        _cell(
            cell_key=f'[100,0,"block_structured","sync_auc",null{i}]',
            lambda_=0.0,
            signal_over_ci=(2.0 if i < 5 else 0.1),
            direction="none",
        )
        for i in range(20)
    )
    sweep = _sweep_with_real_prereg((pre,) + nulls)
    v = derive_verdict(sweep, _prereg())
    assert v.tier == TIER_FAIL
    assert any(e.rule_id == "R2" and not e.passed for e in v.rule_evaluations)


def test_tier_fail_when_direction_is_none() -> None:
    pre = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        signal_over_ci=5.0,
        direction="none",
    )
    null = _cell(
        cell_key='[100,0,"block_structured","sync_auc"]',
        lambda_=0.0,
        signal_over_ci=0.1,
        direction="none",
    )
    sweep = _sweep_with_real_prereg((pre, null))
    v = derive_verdict(sweep, _prereg())
    assert v.tier == TIER_FAIL
    assert any(e.rule_id == "R3" and not e.passed for e in v.rule_evaluations)


# ---------------------------------------------------------------------------
# Anti-overclaim guards
# ---------------------------------------------------------------------------


def test_single_path_pass_flagged_when_only_one_combo_passes() -> None:
    pre_pass = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        substrate_id="block_structured",
        metric_id="sync_auc",
        signal_over_ci=3.0,
    )
    pre_fail = _cell(
        cell_key='[100,0.4,"ricci_flow","tau_onset"]',
        substrate_id="ricci_flow",
        metric_id="tau_onset",
        signal_over_ci=0.5,
    )
    null_a = _cell(
        cell_key='[100,0,"block_structured","sync_auc"]',
        lambda_=0.0,
        signal_over_ci=0.1,
        direction="none",
    )
    null_b = _cell(
        cell_key='[100,0,"ricci_flow","tau_onset"]',
        lambda_=0.0,
        substrate_id="ricci_flow",
        metric_id="tau_onset",
        signal_over_ci=0.1,
        direction="none",
    )
    sweep = _sweep_with_real_prereg((pre_pass, pre_fail, null_a, null_b))
    v = derive_verdict(sweep, _prereg())
    assert v.tier == TIER_PASS
    assert v.single_path_pass is True
    assert any("SINGLE_PATH_PASS" in n for n in v.notes)


def test_null_audit_failure_forces_TIER_FAIL_even_if_rules_pass() -> None:
    pre = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        signal_over_ci=10.0,
    )
    null = _cell(
        cell_key='[100,0,"block_structured","sync_auc"]',
        lambda_=0.0,
        signal_over_ci=0.05,
        direction="none",
    )
    sweep = _sweep_with_real_prereg((pre, null))
    v = derive_verdict(sweep, _prereg(), null_audit_failed=True)
    assert v.tier == TIER_FAIL
    assert any("null_audit_failed" in n for n in v.notes)


# ---------------------------------------------------------------------------
# Determinism + sha behavior
# ---------------------------------------------------------------------------


def test_sha_deterministic_across_calls() -> None:
    pre = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        signal_over_ci=3.0,
    )
    null = _cell(
        cell_key='[100,0,"block_structured","sync_auc"]',
        lambda_=0.0,
        signal_over_ci=0.1,
        direction="none",
    )
    sweep_a = _sweep_with_real_prereg((pre, null))
    sweep_b = _sweep_with_real_prereg((pre, null))
    va = derive_verdict(sweep_a, _prereg())
    vb = derive_verdict(sweep_b, _prereg())
    assert va.sha256 == vb.sha256
    assert va.tier == vb.tier
    assert va.selected_cell_key == vb.selected_cell_key


def test_verdict_result_is_frozen() -> None:
    pre = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        signal_over_ci=3.0,
    )
    null = _cell(
        cell_key='[100,0,"block_structured","sync_auc"]',
        lambda_=0.0,
        signal_over_ci=0.1,
        direction="none",
    )
    v = derive_verdict(_sweep_with_real_prereg((pre, null)), _prereg())
    assert isinstance(v, VerdictResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.tier = "OTHER"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_derive_verdict_rejects_non_SweepResult() -> None:
    with pytest.raises(VerdictInvalid):
        derive_verdict({"not": "a sweep"}, _prereg())  # type: ignore[arg-type]


def test_derive_verdict_rejects_non_preregistration() -> None:
    sweep = _sweep_with_real_prereg(
        (
            _cell(
                cell_key='[100,0.4,"block_structured","sync_auc"]',
                signal_over_ci=3.0,
            ),
            _cell(
                cell_key='[100,0,"block_structured","sync_auc"]',
                lambda_=0.0,
                signal_over_ci=0.1,
                direction="none",
            ),
        )
    )
    with pytest.raises(VerdictInvalid):
        derive_verdict(sweep, {"not": "a prereg"})  # type: ignore[arg-type]


def test_derive_verdict_rejects_mismatched_preregistration_sha() -> None:
    """The sweep's preregistration_sha MUST match the prereg passed in.
    A mismatch means the sweep was run under a different contract."""
    sweep = _sweep(
        (
            _cell(
                cell_key='[100,0.4,"block_structured","sync_auc"]',
                signal_over_ci=3.0,
            ),
        ),
        preregistration_sha="0" * 64,  # different from _prereg()
    )
    with pytest.raises(VerdictInvalid, match="preregistration sha mismatch"):
        derive_verdict(sweep, _prereg())


# ---------------------------------------------------------------------------
# Per-rule numeric constants match the locked YAML
# ---------------------------------------------------------------------------


def test_constants_match_pre_registration_yaml() -> None:
    """The verdict module's numeric constants must match the locked YAML
    (otherwise the deriver and the contract drift)."""
    p = _prereg()
    assert SIGNAL_CI_RATIO_MIN == pytest.approx(p.signal_ci_ratio_threshold)
    assert MARGIN_RELATIVE == 0.05
    # FPR threshold from acceptance R2 prose "FPR(lambda=0) <= 0.05"
    assert FPR_MAX == 0.05


# ---------------------------------------------------------------------------
# Robustness against non-finite values
# ---------------------------------------------------------------------------


def test_non_finite_signal_over_ci_does_not_crash_or_pass() -> None:
    pre = _cell(
        cell_key='[100,0.4,"block_structured","sync_auc"]',
        signal_over_ci=math.inf,
    )
    null = _cell(
        cell_key='[100,0,"block_structured","sync_auc"]',
        lambda_=0.0,
        signal_over_ci=math.nan,
        direction="none",
    )
    v = derive_verdict(_sweep_with_real_prereg((pre, null)), _prereg())
    assert v.tier == TIER_FAIL
    # No rule evaluation should have measured_value=inf or nan stored
    for e in v.rule_evaluations:
        assert math.isfinite(e.measured_value)


def test_empty_sweep_yields_TIER_FAIL() -> None:
    sweep = _sweep_with_real_prereg(())
    v = derive_verdict(sweep, _prereg())
    assert v.tier == TIER_FAIL
    assert v.n_cells_evaluated == 0
    assert v.n_passing_cells == 0
