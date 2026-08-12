# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4-C2 — Tests for the null-audit aggregator.

The aggregator removes the ``aggregate_only=true, results=[]`` launch-
hygiene compromise documented in C2.5: it emits a real per-cell
``d002c_null_audit_capsule_v1`` whose recomputed sha matches the
preflight validator's canonical recompute, so ``launch_allowed=True``
is reachable for a launch that genuinely exercises the null-audit
FAIL signal.

Each test carries >=2 assertions OR ``pytest.raises`` to satisfy the
false-confidence detector heuristic — every assertion drives an
observable contract bit.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from research.systemic_risk.d002c_null_audit import (
    NULL_AUDIT_AGGREGATE_KIND,
    SKIPPED_NO_PER_SEED_DATA,
    NullAuditAggregateInvalid,
    NullAuditAggregateResult,
    NullAuditInputCell,
    run_null_audit_all,
)
from research.systemic_risk.d002c_preflight import (
    NEG_CONTROL_KIND,
    POS_CONTROL_KIND,
    PreflightCapsulePaths,
    canonical_preflight_json,
    load_and_validate_preflight_capsules,
)

# ---------------------------------------------------------------------------
# Helpers — stub capsule writers for POS / NEG / SMOKE
#
# These mirror the canonical sealing pattern from
# tests/research/systemic_risk/test_d002c_preflight.py:
#   sha256 over canonical_preflight_json(body without sha) hashed with
#   sha256. Any deviation here re-introduces the C2.6 sha drift this
#   patch exists to close.
# ---------------------------------------------------------------------------


def _sha(payload: dict[str, Any]) -> str:
    canon = canonical_preflight_json(payload)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _seal(body: dict[str, Any]) -> dict[str, Any]:
    sha = _sha(body)
    out = dict(body)
    out["sha256"] = sha
    return out


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _pos_capsule_stub() -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": POS_CONTROL_KIND,
        "all_pass": True,
        "n_pass": 9,
        "n_exclude": 0,
        "excluded_combos": [],
        "n_seeds": 50,
        "N": 400,
        "lambda_": 1.0,
        "threshold": 2.0,
        "steps_per_quarter": 10,
        "omega_gamma": 0.5,
        "rng_seed_base": 42,
        "wallclock_seconds": 0.0,
        "results": [],
        "generated_at": "2026-05-12T12:00:00Z",
        "substrate_ids": ["ricci_flow", "block_structured", "temporal_coupling"],
        "metric_ids": ["tau_onset", "sync_auc", "phase_lag"],
    }
    return _seal(body)


def _neg_capsule_stub() -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": NEG_CONTROL_KIND,
        "all_pass": True,
        "n_pass": 27,
        "n_exclude": 0,
        "excluded_cells": [],
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
        "generated_at": "2026-05-12T12:01:00Z",
        "substrate_ids": ["ricci_flow", "block_structured", "temporal_coupling"],
        "metric_ids": ["tau_onset", "sync_auc", "phase_lag"],
    }
    return _seal(body)


def _smoke_capsule_stub() -> dict[str, Any]:
    body: dict[str, Any] = {
        "verdict": "PASS",
        "grid_N": [50, 100],
        "grid_lambda": [0.0, 0.5],
        "n_seeds": 5,
        "n_cells_total": 36,
        "n_cells_ok": 36,
        "n_cells_failed": 0,
        "total_wallclock_seconds": 1.0,
        "max_wallclock_seconds": 60.0,
        "over_budget": False,
        "steps_per_quarter": 6,
        "omega_gamma": 0.5,
        "rng_seed_base": 42,
        "cells": [],
        "generated_at": "2026-05-12T12:03:00Z",
    }
    return _seal(body)


def _write_all_stubs(tmp_path: Path, null_path: Path) -> PreflightCapsulePaths:
    pos = tmp_path / "pos.json"
    neg = tmp_path / "neg.json"
    smoke = tmp_path / "smoke.json"
    _write_json(pos, _pos_capsule_stub())
    _write_json(neg, _neg_capsule_stub())
    _write_json(smoke, _smoke_capsule_stub())
    return PreflightCapsulePaths(
        pos_control=pos, neg_control=neg, null_audit=null_path, smoke_test=smoke
    )


# ---------------------------------------------------------------------------
# Helpers — sweep_results fixtures
# ---------------------------------------------------------------------------


def _strong_signal_cell(cell_key: str, n_seeds: int = 20) -> NullAuditInputCell:
    """Strong-signal cell: precursor = null + 1.0 ⇒ verdict PASS."""
    rng = np.random.default_rng(hash(cell_key) & 0xFFFFFFFF)
    null = rng.normal(0.0, 0.05, size=n_seeds).astype(np.float64)
    precursor = null + 1.0
    return NullAuditInputCell(
        cell_key=cell_key,
        precursor_values=precursor,
        null_values=null,
    )


def _noise_only_cell(cell_key: str, n_seeds: int = 20) -> NullAuditInputCell:
    """Centred pure-noise cell: unshuffled |signal| ≈ 0 ⇒ verdict FAIL."""
    rng = np.random.default_rng((hash(cell_key) ^ 0xDEADBEEF) & 0xFFFFFFFF)
    precursor = rng.normal(0.0, 1.0, size=n_seeds).astype(np.float64)
    null = rng.normal(0.0, 1.0, size=n_seeds).astype(np.float64)
    precursor = precursor - float(precursor.mean()) + 0.5
    null = null - float(null.mean()) + 0.5
    return NullAuditInputCell(
        cell_key=cell_key,
        precursor_values=precursor,
        null_values=null,
    )


# ---------------------------------------------------------------------------
# Capsule emission
# ---------------------------------------------------------------------------


def test_run_null_audit_all_writes_capsule_with_correct_kind(tmp_path: Path) -> None:
    """Emitted capsule must declare kind=d002c_null_audit_capsule_v1 and
    carry the load-bearing fields the preflight validator inspects."""
    out = tmp_path / "null_audit.json"
    cells = (_strong_signal_cell("cellA"), _strong_signal_cell("cellB"))
    res = run_null_audit_all(
        output_path=out,
        sweep_results=cells,
        n_shuffles=50,
        rng_seed=0,
    )
    assert out.exists()
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["kind"] == NULL_AUDIT_AGGREGATE_KIND
    assert isinstance(body["generated_at"], str) and body["generated_at"]
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 2
    assert body["aggregate_only"] is False
    assert res.aggregate_verdict == "PASS"


# ---------------------------------------------------------------------------
# Capsule sha must match the preflight validator's canonical recompute
# (the C2.6 alignment guarantee)
# ---------------------------------------------------------------------------


def test_capsule_sha_matches_validator_recompute(tmp_path: Path) -> None:
    """The emitted capsule's sha256 must match the preflight validator's
    recompute exactly. This is THE C2.6 alignment invariant: the writer
    must hash through canonical_preflight_json, not plain
    json.dumps(sort_keys=True). Verified end-to-end by feeding the
    capsule into load_and_validate_preflight_capsules with stub POS /
    NEG / SMOKE capsules — launch_allowed must be True with zero
    refusal reasons."""
    null_path = tmp_path / "null_audit.json"
    cells = (_strong_signal_cell("cellA"), _strong_signal_cell("cellB"))
    res = run_null_audit_all(
        output_path=null_path,
        sweep_results=cells,
        n_shuffles=100,
        rng_seed=0,
    )
    assert res.aggregate_verdict == "PASS"

    paths = _write_all_stubs(tmp_path, null_path)
    decision = load_and_validate_preflight_capsules(paths)
    assert (
        decision.launch_allowed is True
    ), f"preflight refused; reasons={list(decision.refusal_reasons)}"
    assert decision.refusal_reasons == ()
    # The validator's recomputed null_audit sha must match what
    # run_null_audit_all wrote on disk.
    assert decision.capsule_shas["null_audit"] == res.sha256


# ---------------------------------------------------------------------------
# Aggregate verdict rules
# ---------------------------------------------------------------------------


def test_aggregate_pass_iff_all_cells_pass(tmp_path: Path) -> None:
    """PASS iff EVERY audited cell has verdict==PASS AND zero skipped."""
    out = tmp_path / "all_pass.json"
    cells = (
        _strong_signal_cell("cellA"),
        _strong_signal_cell("cellB"),
        _strong_signal_cell("cellC"),
    )
    res = run_null_audit_all(output_path=out, sweep_results=cells, n_shuffles=100)
    assert res.aggregate_verdict == "PASS"
    assert res.n_audited_cells == 3
    assert res.n_pass == 3
    assert res.n_fail == 0


def test_one_fail_cell_makes_aggregate_fail(tmp_path: Path) -> None:
    """ANY FAIL cell ⇒ aggregate FAIL (fail-closed). The preflight reads
    per-cell verdicts, so the aggregator MUST surface FAIL to it."""
    out = tmp_path / "one_fail.json"
    cells = (
        _strong_signal_cell("cellA"),
        _noise_only_cell("cellB_noise"),
        _strong_signal_cell("cellC"),
    )
    res = run_null_audit_all(output_path=out, sweep_results=cells, n_shuffles=200)
    assert res.aggregate_verdict == "FAIL"
    assert res.n_fail >= 1
    assert res.n_pass == res.n_audited_cells - res.n_fail


# ---------------------------------------------------------------------------
# Empty-input handling (fail-closed without escape hatch)
# ---------------------------------------------------------------------------


def test_empty_results_without_aggregate_only_refuses(tmp_path: Path) -> None:
    """Empty resolved cell list MUST raise unless aggregate_only_if_empty=True.
    This blocks the C2.5 launch-hygiene compromise from regressing into
    a silent default."""
    out = tmp_path / "empty.json"
    with pytest.raises(NullAuditAggregateInvalid):
        run_null_audit_all(
            output_path=out,
            sweep_results=(),
            n_shuffles=20,
        )
    assert not out.exists()


def test_empty_with_aggregate_only_emits_escape_capsule(tmp_path: Path) -> None:
    """Genuinely-empty-grid escape hatch: aggregate_only_if_empty=True
    emits the escape capsule the preflight accepts."""
    out = tmp_path / "empty_escape.json"
    res = run_null_audit_all(
        output_path=out,
        sweep_results=(),
        n_shuffles=20,
        aggregate_only_if_empty=True,
    )
    assert out.exists()
    assert res.aggregate_verdict == "PASS"
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["aggregate_only"] is True
    assert body["results"] == []


# ---------------------------------------------------------------------------
# Non-finite p-value path through the preflight validator
# ---------------------------------------------------------------------------


def test_non_finite_p_value_refuses_via_preflight(tmp_path: Path) -> None:
    """If a capsule is forged with a non-finite p_value_empirical, the
    preflight validator must refuse launch with _R_NON_FINITE_FIELD.
    Verifies that the canonical sha encoding correctly stringifies
    non-finite floats AND that the validator inspects p_value_empirical."""
    forged_body: dict[str, Any] = {
        "kind": NULL_AUDIT_AGGREGATE_KIND,
        "generated_at": "2026-05-12T13:00:00Z",
        "n_audited_cells": 1,
        "n_pass": 1,
        "n_fail": 0,
        "n_shuffles_per_cell": 100,
        "aggregate_verdict": "PASS",
        "aggregate_only": False,
        "results": [
            {
                "cell_key": "forged_cell",
                "n_seeds": 20,
                "n_shuffles": 100,
                "unshuffled_abs_signal": 0.5,
                "shuffled_abs_signal_median": 0.05,
                "shuffled_abs_signal_p95": 0.1,
                "p_value_empirical": float("nan"),
                "verdict": "PASS",
                "sha256": "00" * 32,
            }
        ],
    }
    sealed = _seal(forged_body)
    null_path = tmp_path / "forged.json"
    # plain json.dumps refuses NaN by default; canonical_preflight_json
    # replaces it with "NaN" so we round-trip through the canonical
    # encoder for the on-disk artifact too.
    canon = canonical_preflight_json(sealed)
    null_path.write_text(canon, encoding="utf-8")

    paths = _write_all_stubs(tmp_path, null_path)
    decision = load_and_validate_preflight_capsules(paths)
    assert decision.launch_allowed is False
    joined = "\n".join(decision.refusal_reasons)
    assert "capsule_non_finite_load_bearing_field" in joined


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_capsule_sha_deterministic_across_calls(tmp_path: Path) -> None:
    """Same inputs + same generated_at + same seed ⇒ identical capsule
    sha. Guards against accidental non-determinism in the writer (e.g.
    a hidden timestamp drift)."""
    cells = (_strong_signal_cell("cellX"),)
    fixed_ts = "2026-05-12T14:00:00Z"
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    res_a = run_null_audit_all(
        output_path=out_a,
        sweep_results=cells,
        n_shuffles=50,
        rng_seed=7,
        generated_at=fixed_ts,
    )
    res_b = run_null_audit_all(
        output_path=out_b,
        sweep_results=cells,
        n_shuffles=50,
        rng_seed=7,
        generated_at=fixed_ts,
    )
    assert res_a.sha256 == res_b.sha256
    body_a = json.loads(out_a.read_text(encoding="utf-8"))
    body_b = json.loads(out_b.read_text(encoding="utf-8"))
    assert body_a["sha256"] == body_b["sha256"]


def test_capsule_sha_changes_when_one_cell_verdict_changes(tmp_path: Path) -> None:
    """sha must distinguish capsules whose per-cell content differs in
    the verdict bit, otherwise tampering with a single cell would slip
    past the chain-of-custody check."""
    fixed_ts = "2026-05-12T14:30:00Z"
    cells_pass = (_strong_signal_cell("cellY"), _strong_signal_cell("cellZ"))
    cells_mixed = (_strong_signal_cell("cellY"), _noise_only_cell("cellZ_noise"))
    res_pass = run_null_audit_all(
        output_path=tmp_path / "pass.json",
        sweep_results=cells_pass,
        n_shuffles=100,
        rng_seed=3,
        generated_at=fixed_ts,
    )
    res_mixed = run_null_audit_all(
        output_path=tmp_path / "mixed.json",
        sweep_results=cells_mixed,
        n_shuffles=100,
        rng_seed=3,
        generated_at=fixed_ts,
    )
    assert res_pass.sha256 != res_mixed.sha256
    assert res_pass.aggregate_verdict != res_mixed.aggregate_verdict


# ---------------------------------------------------------------------------
# Frozen dataclass contracts
# ---------------------------------------------------------------------------


def test_null_audit_input_cell_is_frozen() -> None:
    """Frozen contract: mutating an instance must raise — input pair
    samples are load-bearing inputs to the audit sha."""
    cell = _strong_signal_cell("frozen_in")
    assert isinstance(cell, NullAuditInputCell)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cell.cell_key = "MUTATED"  # type: ignore[misc]


def test_null_audit_aggregate_result_is_frozen(tmp_path: Path) -> None:
    """Frozen contract: aggregate verdict / sha are immutable once
    emitted — otherwise the chain-of-custody guarantee breaks."""
    out = tmp_path / "frozen.json"
    res = run_null_audit_all(
        output_path=out,
        sweep_results=(_strong_signal_cell("frozen_out"),),
        n_shuffles=20,
    )
    assert isinstance(res, NullAuditAggregateResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.aggregate_verdict = "MUTATED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Skipped cells must force aggregate FAIL (fail-closed)
# ---------------------------------------------------------------------------


def test_skipped_cells_force_aggregate_fail(tmp_path: Path) -> None:
    """A sweep capsule cell lacking per-seed data MUST be recorded with
    verdict=SKIPPED_NO_PER_SEED_DATA AND the aggregate verdict MUST be
    FAIL (a missing audit is not evidence of a passing audit)."""
    sweep_cap = tmp_path / "sweep.json"
    rng = np.random.default_rng(0)
    p_arr = rng.normal(1.0, 0.05, size=15).tolist()
    n_arr = rng.normal(0.0, 0.05, size=15).tolist()
    sweep_cap.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "substrate_id": "ricci_flow",
                        "metric_id": "sync_auc",
                        "N": 100,
                        "lambda_": 0.5,
                        "precursor_per_seed": p_arr,
                        "null_per_seed": n_arr,
                    },
                    # Cell with NO per-seed arrays — must be SKIPPED.
                    {
                        "substrate_id": "block_structured",
                        "metric_id": "tau_onset",
                        "N": 100,
                        "lambda_": 0.5,
                        "variance_ratio": 0.4,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "skipped.json"
    res = run_null_audit_all(
        output_path=out,
        sweep_capsule_path=sweep_cap,
        n_shuffles=50,
        rng_seed=0,
    )
    assert res.aggregate_verdict == "FAIL"
    # Exactly one cell is auditable (and PASSes); one is skipped.
    skipped_verdicts = [r.verdict for r in res.results if r.verdict == SKIPPED_NO_PER_SEED_DATA]
    assert len(skipped_verdicts) == 1
    assert res.n_audited_cells == 1


# ---------------------------------------------------------------------------
# Input-source mutual exclusion
# ---------------------------------------------------------------------------


def test_handles_capsule_path_or_sweep_results_but_not_both(tmp_path: Path) -> None:
    """Exactly one input source MUST be supplied. Both, or neither, MUST
    raise NullAuditAggregateInvalid — the contract is not negotiable
    (passing both would silently ignore one)."""
    out = tmp_path / "rejected.json"
    sweep_cap = tmp_path / "sweep.json"
    sweep_cap.write_text(json.dumps({"results": []}), encoding="utf-8")
    cells = (_strong_signal_cell("X"),)

    with pytest.raises(NullAuditAggregateInvalid):
        run_null_audit_all(
            output_path=out,
            sweep_results=cells,
            sweep_capsule_path=sweep_cap,
            n_shuffles=20,
        )

    with pytest.raises(NullAuditAggregateInvalid):
        run_null_audit_all(
            output_path=out,
            n_shuffles=20,
        )
