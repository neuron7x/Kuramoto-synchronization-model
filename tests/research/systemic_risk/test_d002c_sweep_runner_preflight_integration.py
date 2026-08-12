# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4-D — Integration tests for preflight enforcement in run_sweep."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from research.systemic_risk.d002c_preflight import (
    NEG_CONTROL_KIND,
    NULL_AUDIT_KIND,
    POS_CONTROL_KIND,
    PreflightCapsulePaths,
    PreflightLaunchRefused,
    canonical_preflight_json,
)
from research.systemic_risk.d002c_preregistration import (
    D002CPreregistration,
    load_and_lock,
)
from research.systemic_risk.d002c_sweep_runner import (
    SweepResult,
    run_sweep,
)
from research.systemic_risk.sweep_checkpoint import CheckpointManager, cell_key

CANONICAL_YAML = (
    Path(__file__).resolve().parents[3] / "docs" / "governance" / "D002C_PREREGISTRATION.yaml"
)


# ---------------------------------------------------------------------------
# Capsule fixture helpers (mirror the preflight unit-test fixtures)
# ---------------------------------------------------------------------------


def _sha(payload: dict[str, Any]) -> str:
    canon = canonical_preflight_json(payload)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _seal(capsule_body: dict[str, Any]) -> dict[str, Any]:
    sha = _sha(capsule_body)
    out = dict(capsule_body)
    out["sha256"] = sha
    return out


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _pos_capsule(excluded_combos: list[list[str]] | None = None) -> dict[str, Any]:
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
        "results": [],
        "generated_at": "2026-05-11T12:00:00Z",
        "substrate_ids": ["ricci_flow", "block_structured", "temporal_coupling"],
        "metric_ids": ["tau_onset", "sync_auc", "phase_lag"],
    }
    return _seal(body)


def _neg_capsule(excluded_cells: list[list[Any]] | None = None) -> dict[str, Any]:
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
        "results": [],
        "generated_at": "2026-05-11T12:01:00Z",
        "substrate_ids": ["ricci_flow", "block_structured", "temporal_coupling"],
        "metric_ids": ["tau_onset", "sync_auc", "phase_lag"],
    }
    return _seal(body)


def _null_capsule(verdicts: list[str] | None = None) -> dict[str, Any]:
    verdicts = verdicts if verdicts is not None else ["PASS", "PASS"]
    results = [
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
        for i, v in enumerate(verdicts)
    ]
    body: dict[str, Any] = {
        "kind": NULL_AUDIT_KIND,
        "results": results,
        "n_cells_audited": len(results),
        "all_pass": all(v == "PASS" for v in verdicts),
        "generated_at": "2026-05-11T12:02:00Z",
    }
    return _seal(body)


def _smoke_capsule(verdict: str = "PASS", failed: int = 0) -> dict[str, Any]:
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


def _valid_capsule_paths(
    tmp_path: Path,
    *,
    pos_excluded_combos: list[list[str]] | None = None,
    neg_excluded_cells: list[list[Any]] | None = None,
    smoke_verdict: str = "PASS",
    smoke_failed: int = 0,
    null_verdicts: list[str] | None = None,
) -> PreflightCapsulePaths:
    pos = tmp_path / "pos.json"
    neg = tmp_path / "neg.json"
    null = tmp_path / "null.json"
    smoke = tmp_path / "smoke.json"
    _write_json(pos, _pos_capsule(pos_excluded_combos))
    _write_json(neg, _neg_capsule(neg_excluded_cells))
    _write_json(null, _null_capsule(null_verdicts))
    _write_json(smoke, _smoke_capsule(smoke_verdict, smoke_failed))
    return PreflightCapsulePaths(
        pos_control=pos, neg_control=neg, null_audit=null, smoke_test=smoke
    )


# ---------------------------------------------------------------------------
# Mini prereg + sweep config helpers (mirror legacy test fixture)
# ---------------------------------------------------------------------------


def _mini_prereg() -> D002CPreregistration:
    canonical = load_and_lock(CANONICAL_YAML)
    return D002CPreregistration(
        schema_version=canonical.schema_version,
        version=canonical.version,
        issue=canonical.issue,
        follows=canonical.follows,
        tier_if_pass=canonical.tier_if_pass,
        tier_if_fail=canonical.tier_if_fail,
        acceptance_rule=canonical.acceptance_rule,
        ci_method=canonical.ci_method,
        ci_alpha=canonical.ci_alpha,
        signal_ci_ratio_threshold=canonical.signal_ci_ratio_threshold,
        direction_consistency_min_seeds=2,
        direction_stability_min_fraction=canonical.direction_stability_min_fraction,
        multiple_testing_correction=canonical.multiple_testing_correction,
        n_cells=9,
        effective_alpha_per_cell=canonical.ci_alpha / 9.0,
        n_seeds=4,
        n_bootstrap=4,
        N_grid=(50,),
        lambda_grid=(0.40,),
        substrate_ids=canonical.substrate_ids,
        metric_ids=canonical.metric_ids,
        variance_reduction=canonical.variance_reduction,
        substrate_seed=canonical.substrate_seed,
        forbidden_outputs=canonical.forbidden_outputs,
        preregistration_sha=canonical.preregistration_sha,
        yaml_path=canonical.yaml_path,
    )


def _well_formed_config(prereg: D002CPreregistration) -> dict[str, Any]:
    return {
        "ci_method": prereg.ci_method.value,
        "ci_alpha": prereg.ci_alpha,
        "signal_ci_ratio_threshold": prereg.signal_ci_ratio_threshold,
        "direction_consistency_min_seeds": prereg.direction_consistency_min_seeds,
        "direction_stability_min_fraction": prereg.direction_stability_min_fraction,
        "multiple_testing_correction": prereg.multiple_testing_correction.value,
        "n_seeds": prereg.n_seeds,
        "n_bootstrap": prereg.n_bootstrap,
        "N_grid": list(prereg.N_grid),
        "lambda_grid": list(prereg.lambda_grid),
        "substrate_ids": list(prereg.substrate_ids),
        "metric_ids": list(prereg.metric_ids),
        "variance_reduction": list(prereg.variance_reduction),
        "substrate_seed": prereg.substrate_seed,
        "preregistration_sha": prereg.preregistration_sha,
    }


def _run(
    tmp_path: Path,
    *,
    capsules: PreflightCapsulePaths | None,
    require_preflight: bool = True,
    checkpoint_name: str = "ckpt.json",
) -> SweepResult:
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    return run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=tmp_path / checkpoint_name,
        steps_per_quarter=4,
        preflight_capsules=capsules,
        require_preflight=require_preflight,
    )


# ---------------------------------------------------------------------------
# Required tests
# ---------------------------------------------------------------------------


def test_run_sweep_requires_preflight_when_enabled(tmp_path: Path) -> None:
    """Strict mode: require_preflight=True + no capsules → refuse."""
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        _run(tmp_path, capsules=None, require_preflight=True)
    assert "preflight is required" in str(excinfo.value)
    assert "PreflightCapsulePaths" in str(excinfo.value)


def test_run_sweep_without_preflight_refuses_in_strict_mode(tmp_path: Path) -> None:
    """Same contract, second-axis assertion — fail-closed."""
    with pytest.raises(PreflightLaunchRefused):
        _run(tmp_path, capsules=None, require_preflight=True)
    # And: passing capsules that themselves refuse must still refuse
    paths = _valid_capsule_paths(tmp_path, smoke_verdict="FAIL", smoke_failed=1)
    with pytest.raises(PreflightLaunchRefused):
        _run(tmp_path, capsules=paths, require_preflight=True)


def test_run_sweep_with_valid_preflight_runs_reduced_grid(tmp_path: Path) -> None:
    paths = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    result = _run(tmp_path, capsules=paths)
    # 9-cell grid; POS exclusion removes (block_structured, tau_onset) ⇒ 1 cell
    # at N=50, λ=0.40 → 8 runnable, 1 skipped
    assert result.completed_cells == 8
    assert len(result.skipped_cells) == 1
    assert result.skipped_cells[0].substrate_id == "block_structured"
    assert result.skipped_cells[0].metric_id == "tau_onset"
    assert result.skipped_cells[0].reason == "POS_EXCLUDED_COMBO"


def test_run_sweep_records_skipped_cells_in_checkpoint(tmp_path: Path) -> None:
    paths = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    result = _run(tmp_path, capsules=paths)
    assert len(result.skipped_cells) == 1
    # Re-load checkpoint and confirm SKIPPED_BY_PREFLIGHT entry persists
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    mgr = CheckpointManager(tmp_path / "ckpt.json", sweep_config=cfg)
    ckpt = mgr.load_or_create()
    skipped_keys = [
        k for k, v in ckpt.results.items() if v.payload.get("status") == "SKIPPED_BY_PREFLIGHT"
    ]
    assert len(skipped_keys) == 1
    expected_key = cell_key((50, 0.40, "block_structured", "tau_onset"))
    assert skipped_keys[0] == expected_key


def test_run_sweep_does_not_compute_skipped_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A SKIPPED_BY_PREFLIGHT cell must NOT trigger ``run_one_cell``.

    We instrument :func:`run_one_cell` at the science-layer entry
    point. Instrumenting ``substrate.realize`` would be ambiguous
    because :class:`TemporalKtSubstrate.realize` internally calls
    :class:`BlockStructuredSubstrate.realize` — so the call count at
    the substrate layer is fan-in-amplified. The contract we enforce
    is cell-level: no preflight-skipped cell is ever passed to
    ``run_one_cell``.
    """
    from research.systemic_risk import d002c_sweep_runner as srm

    call_log: list[tuple[str, str, int, float]] = []
    orig_run_one_cell = srm.run_one_cell

    def spy_run_one_cell(*args: Any, **kwargs: Any) -> Any:
        sid = kwargs["substrate"].id
        mid = kwargs["metric"].id
        n = int(kwargs["N"])
        lam = float(kwargs["lambda_"])
        call_log.append((sid, mid, n, lam))
        return orig_run_one_cell(*args, **kwargs)

    monkeypatch.setattr(srm, "run_one_cell", spy_run_one_cell)

    paths = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    result = _run(tmp_path, capsules=paths)
    skipped_ids = {(s.substrate_id, s.metric_id) for s in result.skipped_cells}
    computed_ids = {(c[0], c[1]) for c in call_log}
    # The skipped cell was actually skipped
    assert ("block_structured", "tau_onset") in skipped_ids
    # No computed (substrate, metric) cell is in the skipped set
    assert computed_ids.isdisjoint(skipped_ids)
    # 9-cell mini grid − 1 skipped = 8 computed cells
    assert len(call_log) == 8


def test_run_sweep_resume_preserves_skipped_cells(tmp_path: Path) -> None:
    paths = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    first = _run(tmp_path, capsules=paths, checkpoint_name="ckpt.json")
    # Resume on the same checkpoint — no recompute, same skipped tuple
    resumed = _run(tmp_path, capsules=paths, checkpoint_name="ckpt.json")
    assert first.completed_cells == resumed.completed_cells
    assert len(first.skipped_cells) == len(resumed.skipped_cells)
    assert first.sha256 == resumed.sha256
    assert first.preflight_decision_sha == resumed.preflight_decision_sha


def test_aggregate_sha_includes_preflight_decision_sha(tmp_path: Path) -> None:
    paths_a = _valid_capsule_paths(tmp_path / "a")
    paths_b = _valid_capsule_paths(
        tmp_path / "b",
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    a = _run(tmp_path / "a", capsules=paths_a)
    b = _run(tmp_path / "b", capsules=paths_b)
    # Different preflight decision ⇒ different decision sha ⇒ different
    # aggregate sweep sha
    assert a.preflight_decision_sha != b.preflight_decision_sha
    assert a.sha256 != b.sha256


def test_preflight_capsule_sha_change_changes_sweep_sha(tmp_path: Path) -> None:
    """Tampering with any capsule changes the decision sha, which folds
    into the sweep aggregate sha. We assert this end-to-end."""
    paths = _valid_capsule_paths(tmp_path / "x")
    a = _run(tmp_path / "x", capsules=paths)

    # Build a *different* but *valid* capsule set (different POS exclusion)
    paths2 = _valid_capsule_paths(
        tmp_path / "y",
        pos_excluded_combos=[["ricci_flow", "phase_lag"]],
    )
    b = _run(tmp_path / "y", capsules=paths2)
    assert a.preflight_decision_sha != b.preflight_decision_sha
    assert a.sha256 != b.sha256


def test_tampered_pos_capsule_sha_refuses(tmp_path: Path) -> None:
    paths = _valid_capsule_paths(tmp_path)
    # Forge the POS sha — without recomputing the canonical-JSON sha
    raw = json.loads(paths.pos_control.read_text(encoding="utf-8"))
    raw["sha256"] = "0" * 64
    _write_json(paths.pos_control, raw)
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        _run(tmp_path, capsules=paths)
    assert "capsule_sha256_mismatch" in str(excinfo.value)


def test_tampered_neg_capsule_sha_refuses(tmp_path: Path) -> None:
    paths = _valid_capsule_paths(tmp_path)
    raw = json.loads(paths.neg_control.read_text(encoding="utf-8"))
    raw["sha256"] = "0" * 64
    _write_json(paths.neg_control, raw)
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        _run(tmp_path, capsules=paths)
    assert "capsule_sha256_mismatch" in str(excinfo.value)


def test_smoke_pass_but_null_fail_refuses(tmp_path: Path) -> None:
    paths = _valid_capsule_paths(tmp_path, null_verdicts=["PASS", "FAIL"])
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        _run(tmp_path, capsules=paths)
    assert "null_audit_verdict_not_pass" in str(excinfo.value)


def test_all_capsules_pass_but_unknown_cell_refuses(tmp_path: Path) -> None:
    paths = _valid_capsule_paths(
        tmp_path,
        neg_excluded_cells=[["block_structured", "tau_onset", 99999]],
    )
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        _run(tmp_path, capsules=paths)
    assert "capsule_unknown_N" in str(excinfo.value)


def test_excluded_cell_cannot_reappear_as_computed(tmp_path: Path) -> None:
    """A SKIPPED_BY_PREFLIGHT cell on disk must NOT be turned into a
    computed SweepCellOutput by the second run."""
    paths = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    first = _run(tmp_path, capsules=paths, checkpoint_name="ckpt.json")
    second = _run(tmp_path, capsules=paths, checkpoint_name="ckpt.json")
    expected_key = cell_key((50, 0.40, "block_structured", "tau_onset"))
    runnable_keys_first = {r.cell_key for r in first.results}
    runnable_keys_second = {r.cell_key for r in second.results}
    assert expected_key not in runnable_keys_first
    assert expected_key not in runnable_keys_second
    # And the skipped cell carries the source capsule sha
    assert all(s.source_capsule_sha256 for s in second.skipped_cells)


# ---------------------------------------------------------------------------
# Determinism + frozen-result invariants under preflight
# ---------------------------------------------------------------------------


def test_run_sweep_with_preflight_is_deterministic(tmp_path: Path) -> None:
    paths_a = _valid_capsule_paths(tmp_path / "a")
    paths_b = _valid_capsule_paths(tmp_path / "b")
    a = _run(tmp_path / "a", capsules=paths_a, checkpoint_name="a.json")
    b = _run(tmp_path / "b", capsules=paths_b, checkpoint_name="b.json")
    assert a.sha256 == b.sha256
    assert a.preflight_decision_sha == b.preflight_decision_sha


def test_run_sweep_skipped_cells_count_matches_expectation(tmp_path: Path) -> None:
    """Cross-check: POS excludes 1 combo ⇒ removes 1 cell (1 N × 1 λ).
    NEG excludes 1 different cell ⇒ removes 1 more cell.
    Total runnable = 9 − 2 = 7."""
    paths = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
        neg_excluded_cells=[["ricci_flow", "sync_auc", 50]],
    )
    result = _run(tmp_path, capsules=paths)
    assert result.completed_cells == 7
    assert len(result.skipped_cells) == 2
    reasons = sorted(s.reason for s in result.skipped_cells)
    assert reasons == ["NEG_EXCLUDED_CELL", "POS_EXCLUDED_COMBO"]


# ---------------------------------------------------------------------------
# Codex P1 regression (2026-05-12) — checkpoint drift under capsule rotation
#
# Three drift modes are fail-closed: if the persisted checkpoint state
# contradicts the CURRENT preflight decision, the runner must refuse
# launch rather than silently return an incomplete / stale grid.
# ---------------------------------------------------------------------------


def test_checkpoint_drift_persisted_skipped_now_runnable_refuses(
    tmp_path: Path,
) -> None:
    """Run 1: POS excludes (block_structured, tau_onset) → cell saved as
    SKIPPED. Run 2: POS exclusion lifted (no excluded combos) → cell is
    now runnable. The runner MUST refuse, because resuming would treat
    the previously-skipped cell as already completed and never compute it,
    silently emitting an incomplete sweep under a fresh aggregate sha."""
    paths_strict = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    _run(tmp_path, capsules=paths_strict, checkpoint_name="ckpt.json")
    # New capsules — exclusion removed — written to the same dir; the
    # checkpoint still carries the SKIPPED row from run 1.
    paths_relaxed = _valid_capsule_paths(tmp_path)
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        _run(tmp_path, capsules=paths_relaxed, checkpoint_name="ckpt.json")
    msg = str(excinfo.value)
    assert "persisted_skipped_cell_no_longer_excluded" in msg
    assert "block_structured" in msg
    assert "tau_onset" in msg


def test_checkpoint_drift_persisted_computed_now_excluded_refuses(
    tmp_path: Path,
) -> None:
    """Run 1: no exclusions → all 9 cells computed. Run 2: POS now
    excludes (block_structured, tau_onset) → that cell is in the
    skipped tuple. The on-disk record is a computed result; the new
    decision contradicts it. Refuse rather than rewrite the audit row."""
    paths_open = _valid_capsule_paths(tmp_path)
    _run(tmp_path, capsules=paths_open, checkpoint_name="ckpt.json")
    paths_strict = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        _run(tmp_path, capsules=paths_strict, checkpoint_name="ckpt.json")
    msg = str(excinfo.value)
    assert "persisted_computed_cell_now_excluded" in msg


def test_checkpoint_drift_source_capsule_sha_change_refuses(
    tmp_path: Path,
) -> None:
    """Run 1: POS capsule excludes (block_structured, tau_onset) → cell
    skipped with source_capsule_sha256 = sha_A. Run 2: POS capsule
    rotated to a structurally equivalent capsule with a different sha
    (e.g. additional metadata field) but the SAME exclusion → still
    excluded but the audit provenance changed. The runner must refuse
    rather than silently rewrite the source_capsule_sha256 row."""
    paths_run1 = _valid_capsule_paths(
        tmp_path / "run1",
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    # Copy the four capsules to a fresh run2 directory but rewrite the
    # POS capsule with a different generated_at (so its sha shifts)
    # while preserving the same excluded_combos.
    import json
    import shutil

    run2_dir = tmp_path / "run2"
    run2_dir.mkdir()
    for name in ("pos", "neg", "null", "smoke"):
        src = tmp_path / "run1" / f"{name}.json"
        dst = run2_dir / f"{name}.json"
        if name == "pos":
            payload = json.loads(src.read_text(encoding="utf-8"))
            # Recompute sha-bearing canonical form with a new generated_at
            payload["generated_at"] = "2026-05-12T12:00:00Z"
            payload.pop("sha256", None)
            import hashlib

            from research.systemic_risk.d002c_preflight import (
                canonical_preflight_json,
            )

            payload["sha256"] = hashlib.sha256(
                canonical_preflight_json(payload).encode("utf-8")
            ).hexdigest()
            dst.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        else:
            shutil.copy(src, dst)
    paths_run2 = PreflightCapsulePaths(
        pos_control=run2_dir / "pos.json",
        neg_control=run2_dir / "neg.json",
        null_audit=run2_dir / "null.json",
        smoke_test=run2_dir / "smoke.json",
    )
    # First run — populate the checkpoint with the original POS sha
    ckpt = run2_dir / "ckpt.json"
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=ckpt,
        steps_per_quarter=4,
        preflight_capsules=paths_run1,
        require_preflight=True,
    )
    # Resume against the rotated POS capsule — refuse
    with pytest.raises(PreflightLaunchRefused) as excinfo:
        run_sweep(
            preregistration=prereg,
            sweep_config=cfg,
            checkpoint_path=ckpt,
            steps_per_quarter=4,
            preflight_capsules=paths_run2,
            require_preflight=True,
        )
    msg = str(excinfo.value)
    assert "persisted_skipped_cell_source_capsule_sha_drifted" in msg


def test_checkpoint_drift_clean_resume_passes(tmp_path: Path) -> None:
    """The drift check must NOT false-positive on a clean resume where
    the capsules are byte-identical between run 1 and run 2."""
    paths = _valid_capsule_paths(
        tmp_path,
        pos_excluded_combos=[["block_structured", "tau_onset"]],
    )
    first = _run(tmp_path, capsules=paths, checkpoint_name="ckpt.json")
    second = _run(tmp_path, capsules=paths, checkpoint_name="ckpt.json")
    assert first.sha256 == second.sha256
    assert len(first.skipped_cells) == len(second.skipped_cells)
