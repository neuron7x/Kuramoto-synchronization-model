# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4-D — Unit tests for the preflight enforcement layer."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from research.systemic_risk.d002c_preflight import (
    NEG_CONTROL_KIND,
    NULL_AUDIT_KIND,
    POS_CONTROL_KIND,
    CapsuleShaMismatch,
    PreflightCapsulePaths,
    PreflightLaunchRefused,
    RunnableCell,
    SkippedCell,
    apply_preflight_to_grid,
    assert_preflight_launch_allowed,
    canonical_preflight_json,
    load_and_validate_preflight_capsules,
    verify_capsule_sha256,
)

# ---------------------------------------------------------------------------
# Capsule fixture helpers
# ---------------------------------------------------------------------------


def _sha(payload: dict[str, Any]) -> str:
    """Mirror the preflight canonical-JSON discipline."""
    canon = canonical_preflight_json(payload)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _seal(capsule_body: dict[str, Any]) -> dict[str, Any]:
    """Compute sha256 over the payload (sans the sha field) and return
    a sealed capsule whose verify_capsule_sha256 succeeds."""
    sha = _sha(capsule_body)
    out = dict(capsule_body)
    out["sha256"] = sha
    return out


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _pos_capsule(
    *,
    excluded_combos: list[list[str]] | None = None,
    extra_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": POS_CONTROL_KIND,
        "all_pass": excluded_combos in (None, []),
        "n_pass": 9,
        "n_exclude": 0 if not excluded_combos else len(excluded_combos),
        "excluded_combos": excluded_combos or [],
        "n_seeds": 50,
        "N": 400,
        "lambda_": 1.0,
        "threshold": 2.0,
        "steps_per_quarter": 10,
        "omega_gamma": 0.5,
        "rng_seed_base": 42,
        "wallclock_seconds": 0.0,
        "results": extra_results
        or [
            {
                "substrate_id": "block_structured",
                "metric_id": "sync_auc",
                "N": 400,
                "lambda_": 1.0,
                "n_seeds": 50,
                "signal_mean": 1.0,
                "signal_std": 0.1,
                "signal_ci_ratio": 70.0,
                "threshold": 2.0,
                "verdict": "PASS",
                "censoring_fraction": 0.0,
                "wallclock_seconds": 0.1,
                "sha256": "deadbeef" * 8,
            }
        ],
        "generated_at": "2026-05-11T12:00:00Z",
        "substrate_ids": ["ricci_flow", "block_structured", "temporal_coupling"],
        "metric_ids": ["tau_onset", "sync_auc", "phase_lag"],
    }
    return _seal(body)


def _neg_capsule(
    *,
    excluded_cells: list[list[Any]] | None = None,
    extra_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": NEG_CONTROL_KIND,
        "all_pass": excluded_cells in (None, []),
        "n_pass": 27,
        "n_exclude": 0 if not excluded_cells else len(excluded_cells),
        "excluded_cells": excluded_cells or [],
        "n_seeds": 50,
        "N_grid": [50, 100, 200],
        "alpha_bonferroni": 2.31e-4,
        "tolerance": 1e-3,
        "steps_per_quarter": 10,
        "omega_gamma": 0.5,
        "rng_seed_base": 42,
        "independent_seed_stride": 10000,
        "wallclock_seconds": 0.0,
        "results": extra_results
        or [
            {
                "substrate_id": "block_structured",
                "metric_id": "sync_auc",
                "N": 50,
                "lambda_": 0.0,
                "n_seeds": 50,
                "false_positive_count": 0,
                "fpr": 0.0,
                "alpha_bonferroni": 2.31e-4,
                "threshold_tolerance": 1e-3,
                "verdict": "PASS",
                "wallclock_seconds": 0.1,
                "sha256": "cafebabe" * 8,
            }
        ],
        "generated_at": "2026-05-11T12:01:00Z",
        "substrate_ids": ["ricci_flow", "block_structured", "temporal_coupling"],
        "metric_ids": ["tau_onset", "sync_auc", "phase_lag"],
    }
    return _seal(body)


def _null_capsule(*, verdicts: list[str] | None = None) -> dict[str, Any]:
    verdicts = verdicts if verdicts is not None else ["PASS", "PASS"]
    results: list[dict[str, Any]] = []
    for i, v in enumerate(verdicts):
        results.append(
            {
                "n_seeds": 20,
                "n_shuffles": 100,
                "unshuffled_abs_signal": 0.5,
                "shuffled_abs_signal_median": 0.05,
                "shuffled_abs_signal_p95": 0.1,
                "unshuffled_greater_than_median": True,
                "p_value_empirical": 0.01 if v == "PASS" else 0.5,
                "verdict": v,
                "rng_seed": 42 + i,
                "p_value_threshold": 0.05,
                "sha256": f"{i:0>64x}",
            }
        )
    body: dict[str, Any] = {
        "kind": NULL_AUDIT_KIND,
        "results": results,
        "n_cells_audited": len(results),
        "all_pass": all(v == "PASS" for v in verdicts),
        "generated_at": "2026-05-11T12:02:00Z",
    }
    return _seal(body)


def _smoke_capsule(*, verdict: str = "PASS", failed: int = 0) -> dict[str, Any]:
    body: dict[str, Any] = {
        "verdict": verdict,
        "grid_N": [50, 100],
        "grid_lambda": [0.0, 0.5],
        "n_seeds": 5,
        "n_cells_total": 36,
        "n_cells_ok": 36 - failed,
        "n_cells_failed": failed,
        "total_wallclock_seconds": 1.0,
        "max_wallclock_seconds": 60.0,
        "over_budget": False,
        "steps_per_quarter": 6,
        "omega_gamma": 0.5,
        "rng_seed_base": 42,
        "cells": [],
        "generated_at": "2026-05-11T12:03:00Z",
    }
    return _seal(body)


def _valid_paths(tmp_path: Path) -> PreflightCapsulePaths:
    pos = tmp_path / "pos.json"
    neg = tmp_path / "neg.json"
    null = tmp_path / "null.json"
    smoke = tmp_path / "smoke.json"
    _write_json(pos, _pos_capsule())
    _write_json(neg, _neg_capsule())
    _write_json(null, _null_capsule())
    _write_json(smoke, _smoke_capsule())
    return PreflightCapsulePaths(
        pos_control=pos, neg_control=neg, null_audit=null, smoke_test=smoke
    )


# ---------------------------------------------------------------------------
# Missing-capsule refusals
# ---------------------------------------------------------------------------


def test_missing_pos_capsule_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    paths.pos_control.unlink()
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_missing_file" in r for r in decision.refusal_reasons)
    assert decision.capsule_shas["pos_control"] == "UNVERIFIED"


def test_missing_neg_capsule_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    paths.neg_control.unlink()
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_missing_file" in r for r in decision.refusal_reasons)
    assert decision.capsule_shas["neg_control"] == "UNVERIFIED"


def test_missing_null_capsule_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    paths.null_audit.unlink()
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_missing_file" in r for r in decision.refusal_reasons)
    assert decision.capsule_shas["null_audit"] == "UNVERIFIED"


def test_missing_smoke_capsule_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    paths.smoke_test.unlink()
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_missing_file" in r for r in decision.refusal_reasons)
    assert decision.capsule_shas["smoke_test"] == "UNVERIFIED"


# ---------------------------------------------------------------------------
# Malformed-capsule refusals
# ---------------------------------------------------------------------------


def test_bad_json_capsule_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    paths.pos_control.write_text("{not-json", encoding="utf-8")
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_bad_json" in r for r in decision.refusal_reasons)


def test_bad_kind_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    bad = _pos_capsule()
    bad["kind"] = "wrong_kind_v0"
    bad["sha256"] = _sha({k: v for k, v in bad.items() if k != "sha256"})
    _write_json(paths.pos_control, bad)
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_kind_mismatch" in r for r in decision.refusal_reasons)


def test_bad_sha_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    bad = _pos_capsule()
    bad["sha256"] = "0" * 64  # forged
    _write_json(paths.pos_control, bad)
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_sha256_mismatch" in r for r in decision.refusal_reasons)


# ---------------------------------------------------------------------------
# Verdict refusals
# ---------------------------------------------------------------------------


def test_smoke_fail_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(paths.smoke_test, _smoke_capsule(verdict="FAIL", failed=3))
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("smoke_verdict_not_pass" in r for r in decision.refusal_reasons)


def test_null_fail_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(paths.null_audit, _null_capsule(verdicts=["PASS", "FAIL"]))
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("null_audit_verdict_not_pass" in r for r in decision.refusal_reasons)


def test_null_audit_empty_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(paths.null_audit, _null_capsule(verdicts=[]))
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("null_audit_empty_results" in r for r in decision.refusal_reasons)


# ---------------------------------------------------------------------------
# POS / NEG exclusion semantics
# ---------------------------------------------------------------------------


def test_pos_excluded_combo_removes_all_matching_cells(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(
        paths.pos_control,
        _pos_capsule(excluded_combos=[["block_structured", "tau_onset"]]),
    )
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is True
    assert decision.excluded_combos == (("block_structured", "tau_onset"),)

    # Build a tiny grid spanning two N values and the excluded combo
    full = [
        (50, 0.0, "block_structured", "tau_onset"),
        (100, 0.5, "block_structured", "tau_onset"),
        (50, 0.0, "ricci_flow", "sync_auc"),
    ]
    runnable, skipped = apply_preflight_to_grid(full, decision)
    assert len(runnable) == 1
    assert runnable[0].substrate_id == "ricci_flow"
    assert len(skipped) == 2
    assert all(s.reason == "POS_EXCLUDED_COMBO" for s in skipped)
    assert all(s.source_capsule == "pos_control" for s in skipped)


def test_neg_excluded_cell_removes_exact_cell_only(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(
        paths.neg_control,
        _neg_capsule(excluded_cells=[["block_structured", "tau_onset", 50]]),
    )
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is True
    assert decision.excluded_cells == (("block_structured", "tau_onset", 50),)

    full = [
        (50, 0.0, "block_structured", "tau_onset"),  # excluded
        (100, 0.0, "block_structured", "tau_onset"),  # different N — KEPT
        (50, 0.0, "block_structured", "sync_auc"),  # different metric — KEPT
    ]
    runnable, skipped = apply_preflight_to_grid(full, decision)
    assert len(runnable) == 2
    assert len(skipped) == 1
    assert skipped[0].N == 50
    assert skipped[0].reason == "NEG_EXCLUDED_CELL"


# ---------------------------------------------------------------------------
# Identity validation
# ---------------------------------------------------------------------------


def test_unknown_substrate_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(
        paths.pos_control,
        _pos_capsule(excluded_combos=[["NONEXISTENT_SUBSTRATE", "tau_onset"]]),
    )
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_unknown_substrate_id" in r for r in decision.refusal_reasons)


def test_unknown_metric_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(
        paths.pos_control,
        _pos_capsule(excluded_combos=[["block_structured", "NONEXISTENT_METRIC"]]),
    )
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_unknown_metric_id" in r for r in decision.refusal_reasons)


def test_unknown_N_refuses_launch(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(
        paths.neg_control,
        _neg_capsule(excluded_cells=[["block_structured", "tau_onset", 99999]]),
    )
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_unknown_N" in r for r in decision.refusal_reasons)


# ---------------------------------------------------------------------------
# Determinism + frozen invariants
# ---------------------------------------------------------------------------


def test_preflight_decision_sha_is_deterministic(tmp_path: Path) -> None:
    # Two identical capsule sets in different tmp dirs → same decision sha
    paths_a = _valid_paths(tmp_path / "a")
    paths_b = _valid_paths(tmp_path / "b")
    d_a = load_and_validate_preflight_capsules(paths_a)
    d_b = load_and_validate_preflight_capsules(paths_b)
    assert d_a.launch_allowed is True
    assert d_b.launch_allowed is True
    assert d_a.sha256 == d_b.sha256
    assert d_a.capsule_shas == d_b.capsule_shas


def test_preflight_decision_is_frozen(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    decision = load_and_validate_preflight_capsules(paths)
    assert dataclasses.is_dataclass(decision)
    assert decision.launch_allowed is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.launch_allowed = False  # type: ignore[misc]


def test_skipped_cell_and_runnable_cell_frozen() -> None:
    s = SkippedCell(
        cell_key='[50,0.0,"x","y"]',
        substrate_id="x",
        metric_id="y",
        N=50,
        lambda_=0.0,
        reason="POS_EXCLUDED_COMBO",
        source_capsule="pos_control",
        source_capsule_sha256="ab" * 32,
    )
    r = RunnableCell(
        cell_key='[100,0.5,"x","y"]',
        substrate_id="x",
        metric_id="y",
        N=100,
        lambda_=0.5,
    )
    assert s.reason == "POS_EXCLUDED_COMBO"
    assert r.N == 100
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.N = 99  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.N = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Capsule sha contract (matches emitter discipline)
# ---------------------------------------------------------------------------


def test_capsule_sha_recompute_matches_emitter() -> None:
    body = {
        "kind": POS_CONTROL_KIND,
        "all_pass": True,
        "n_pass": 9,
        "n_exclude": 0,
        "excluded_combos": [],
        "generated_at": "2026-05-11T12:00:00Z",
    }
    sealed = _seal(body)
    # Recompute must match the seal exactly
    recomputed = verify_capsule_sha256(sealed)
    assert recomputed == sealed["sha256"]
    # And mutating any field must break the recomputation
    mutated = dict(sealed)
    mutated["all_pass"] = False
    with pytest.raises(CapsuleShaMismatch):
        verify_capsule_sha256(mutated)


def test_capsule_sha_missing_sha_field_raises() -> None:
    body: dict[str, Any] = {"kind": POS_CONTROL_KIND}
    with pytest.raises(CapsuleShaMismatch):
        verify_capsule_sha256(body)
    with pytest.raises(CapsuleShaMismatch):
        verify_capsule_sha256({"kind": POS_CONTROL_KIND, "sha256": 12345})


# ---------------------------------------------------------------------------
# Canonical-JSON behaviour
# ---------------------------------------------------------------------------


def test_canonical_json_handles_non_finite_sentinel() -> None:
    payload_a = {"x": float("nan"), "y": float("inf"), "z": float("-inf")}
    payload_b = {"x": float("nan"), "y": float("inf"), "z": float("-inf")}
    canon_a = canonical_preflight_json(payload_a)
    canon_b = canonical_preflight_json(payload_b)
    assert canon_a == canon_b
    assert "NaN" in canon_a
    assert "Infinity" in canon_a
    assert "-Infinity" in canon_a


def test_canonical_json_is_sort_keys_stable() -> None:
    a = canonical_preflight_json({"b": 1, "a": 2, "c": [3, 4]})
    b = canonical_preflight_json({"c": [3, 4], "a": 2, "b": 1})
    assert a == b
    # Tight separators — no spaces
    assert ", " not in a
    assert ": " not in a


# ---------------------------------------------------------------------------
# Launch-refusal raise path
# ---------------------------------------------------------------------------


def test_assert_preflight_launch_allowed_raises_with_reasons(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    paths.pos_control.unlink()
    decision = load_and_validate_preflight_capsules(paths)
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        assert_preflight_launch_allowed(decision)
    assert "preflight launch refused" in str(excinfo.value)
    assert "capsule_missing_file" in str(excinfo.value)


def test_assert_preflight_launch_allowed_noop_on_valid(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    decision = load_and_validate_preflight_capsules(paths)
    # Must not raise; must be content-addressed
    assert_preflight_launch_allowed(decision)
    assert decision.launch_allowed is True
    assert len(decision.refusal_reasons) == 0


# ---------------------------------------------------------------------------
# Combined-failure accumulation
# ---------------------------------------------------------------------------


def test_multiple_failures_all_accumulated(tmp_path: Path) -> None:
    """Three independent failures must all surface in refusal_reasons —
    no first-fail short-circuit."""
    paths = _valid_paths(tmp_path)
    paths.pos_control.unlink()
    _write_json(paths.smoke_test, _smoke_capsule(verdict="FAIL", failed=1))
    _write_json(paths.null_audit, _null_capsule(verdicts=["FAIL"]))
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    reasons = "\n".join(decision.refusal_reasons)
    assert "capsule_missing_file" in reasons
    assert "smoke_verdict_not_pass" in reasons
    assert "null_audit_verdict_not_pass" in reasons


# ---------------------------------------------------------------------------
# Non-finite numeric field in pos/neg result
# ---------------------------------------------------------------------------


def test_non_finite_numeric_field_refuses(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    bad_pos = _pos_capsule(
        extra_results=[
            {
                "substrate_id": "block_structured",
                "metric_id": "sync_auc",
                "N": 400,
                "lambda_": 1.0,
                "n_seeds": 50,
                "signal_mean": float("nan"),  # forbidden
                "signal_std": 0.1,
                "signal_ci_ratio": float("inf"),  # forbidden
                "threshold": 2.0,
                "verdict": "PASS",
                "censoring_fraction": 0.0,
                "wallclock_seconds": 0.1,
                "sha256": "deadbeef" * 8,
            }
        ]
    )
    _write_json(paths.pos_control, bad_pos)
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_non_finite_load_bearing_field" in r for r in decision.refusal_reasons)


# ---------------------------------------------------------------------------
# Grid reduction: pure POS / pure NEG / both
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("excluded_combos", "excluded_cells", "n_runnable", "n_skipped"),
    [
        ([], [], 4, 0),
        ([["block_structured", "tau_onset"]], [], 2, 2),
        ([], [["block_structured", "tau_onset", 50]], 3, 1),
        ([["block_structured", "tau_onset"]], [["ricci_flow", "sync_auc", 50]], 1, 3),
    ],
)
def test_parametrized_grid_reduction(
    tmp_path: Path,
    excluded_combos: list[list[str]],
    excluded_cells: list[list[Any]],
    n_runnable: int,
    n_skipped: int,
) -> None:
    paths = _valid_paths(tmp_path)
    _write_json(paths.pos_control, _pos_capsule(excluded_combos=excluded_combos))
    _write_json(paths.neg_control, _neg_capsule(excluded_cells=excluded_cells))
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is True
    full = [
        (50, 0.0, "block_structured", "tau_onset"),
        (100, 0.0, "block_structured", "tau_onset"),
        (50, 0.0, "ricci_flow", "sync_auc"),
        (50, 0.0, "temporal_coupling", "phase_lag"),
    ]
    runnable, skipped = apply_preflight_to_grid(full, decision)
    assert len(runnable) == n_runnable
    assert len(skipped) == n_skipped


# ---------------------------------------------------------------------------
# Decision sha changes when any capsule changes
# ---------------------------------------------------------------------------


def test_decision_sha_changes_with_pos_capsule(tmp_path: Path) -> None:
    paths_a = _valid_paths(tmp_path / "a")
    paths_b = _valid_paths(tmp_path / "b")
    # Force one to carry an exclusion
    _write_json(
        paths_b.pos_control,
        _pos_capsule(excluded_combos=[["block_structured", "tau_onset"]]),
    )
    d_a = load_and_validate_preflight_capsules(paths_a)
    d_b = load_and_validate_preflight_capsules(paths_b)
    assert d_a.launch_allowed is True
    assert d_b.launch_allowed is True
    assert d_a.sha256 != d_b.sha256


def test_apply_preflight_preserves_cell_keys(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    decision = load_and_validate_preflight_capsules(paths)
    full = [
        (50, 0.5, "block_structured", "sync_auc"),
        (100, 0.0, "ricci_flow", "tau_onset"),
    ]
    runnable, skipped = apply_preflight_to_grid(full, decision)
    assert len(runnable) == 2
    assert len(skipped) == 0
    # Cell keys must follow the canonical sweep_checkpoint.cell_key form
    assert all(rc.cell_key.startswith("[") and rc.cell_key.endswith("]") for rc in runnable)
    assert math.isfinite(runnable[0].lambda_)


def test_missing_generated_at_refuses(tmp_path: Path) -> None:
    paths = _valid_paths(tmp_path)
    bad = _pos_capsule()
    del bad["generated_at"]
    bad["sha256"] = _sha({k: v for k, v in bad.items() if k != "sha256"})
    _write_json(paths.pos_control, bad)
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    assert any("capsule_missing_generated_at" in r for r in decision.refusal_reasons)
