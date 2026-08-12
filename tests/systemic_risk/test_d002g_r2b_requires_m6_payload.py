# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""P0-2 Codex review fix — R2-B aggregator MUST reject non-M6 payloads.

Attack
------
Before the fix, ``evaluate_r2b`` validated ``lambda_ > 0`` but never
checked ``row.null_strategy``. The aggregator then unconditionally
stamped ``null_strategy="M6_PLACEBO_COUPLING"`` on every R2BCellResult
in the output. A mixed / legacy / M1 input therefore silently produced
an R2-B verdict labeled as M6 — provenance was being **output-invented**
rather than **input-validated**.

Fix
---
``_r2b_provenance_preflight`` runs BEFORE any per-cell statistic. It
requires every row to:

  * carry the full schema fields (``null_strategy``, ``lambda_``,
    ``substrate_id``, ``cell_key``, ``metric_id``, ``N``,
    ``precursor_values``, ``null_values``);
  * carry ``null_strategy == "M6_PLACEBO_COUPLING"``.

ANY violation → no statistics computed → verdict
``R2B_INVALID_NON_M6_PAYLOAD_VERDICT``. The audit-of-failure is carried
in the verdict's ``metadata['r2b_provenance_audit']``.

Properties tested (all P0):
  1. pure M6 cohort: preflight passes; verdict ∈ {PASS, FAIL, INDETERMINATE}.
  2. M1 row in M6 cohort: fail-closed; verdict == INVALID; no stats.
  3. legacy default-strategy row: fail-closed; verdict == INVALID.
  4. mixed M6 + M1: fail-closed; verdict == INVALID.
  5. aggregator NEVER stamps M6 strategy on invalid input (cell_results
     is empty on the invalid path).
  6. invalid provenance NEVER yields PASS.

The contract is the input-validation discipline; the fail-closed verdict
is the observable channel for consumers.
"""

from __future__ import annotations

import hashlib

import numpy as np

from research.systemic_risk.d002c_preflight import canonical_preflight_json
from research.systemic_risk.d002c_sweep_runner import (
    PAYLOAD_SCHEMA_V2,
    NullAuditCellPayload,
)
from research.systemic_risk.d002g_r2b_gate import (
    R2B_INDETERMINATE_VERDICT,
    R2B_INVALID_NON_M6_PAYLOAD_VERDICT,
    evaluate_r2b,
)


def _payload(
    *,
    cell_key: str,
    null_strategy: str,
    precursor: np.ndarray,
    null: np.ndarray,
    payload_schema: str = PAYLOAD_SCHEMA_V2,
    null_seed: int | None = 42,
) -> NullAuditCellPayload:
    p_vals = tuple(float(x) for x in precursor)
    n_vals = tuple(float(x) for x in null)
    sha_input = {
        "cell_key": cell_key,
        "N": 50,
        "lambda_": 0.5,
        "substrate_id": "ricci_flow",
        "metric_id": "sync_auc",
        "seed_ids": list(range(len(p_vals))),
        "precursor_values": list(p_vals),
        "null_values": list(n_vals),
        "paired_by_seed": True,
        "crn_identity_hash": "stub-p02-" + cell_key,
        "metric_version": "test_v1",
        "substrate_version": "test_v1",
    }
    sha = hashlib.sha256(canonical_preflight_json(sha_input).encode("utf-8")).hexdigest()
    return NullAuditCellPayload(
        cell_key=cell_key,
        N=50,
        lambda_=0.5,
        substrate_id="ricci_flow",
        metric_id="sync_auc",
        seed_ids=tuple(range(len(p_vals))),
        precursor_values=p_vals,
        null_values=n_vals,
        paired_by_seed=True,
        crn_identity_hash="stub-p02-" + cell_key,
        metric_version="test_v1",
        substrate_version="test_v1",
        generated_at="",
        sha256=sha,
        payload_schema=payload_schema,
        null_strategy=null_strategy,
        null_seed=null_seed,
    )


def _m6_row(i: int, rng: np.random.Generator) -> NullAuditCellPayload:
    prec = rng.normal(loc=1.0, scale=0.1, size=20)
    nul = rng.normal(loc=0.0, scale=0.1, size=20)
    return _payload(
        cell_key=f"m6_{i}", null_strategy="M6_PLACEBO_COUPLING", precursor=prec, null=nul
    )


def _m1_row(i: int, rng: np.random.Generator) -> NullAuditCellPayload:
    prec = rng.normal(loc=1.0, scale=0.1, size=20)
    nul = rng.normal(loc=0.0, scale=0.1, size=20)
    return _payload(
        cell_key=f"m1_{i}", null_strategy="M1_INDEPENDENT_SEED", precursor=prec, null=nul
    )


def _legacy_row(i: int, rng: np.random.Generator) -> NullAuditCellPayload:
    prec = rng.normal(loc=1.0, scale=0.1, size=20)
    nul = rng.normal(loc=0.0, scale=0.1, size=20)
    return _payload(
        cell_key=f"legacy_{i}",
        null_strategy="D002C_PAIRED_CRN_LEGACY",
        precursor=prec,
        null=nul,
        null_seed=None,
    )


# ---------------------------------------------------------------------------
# Property 1: pure M6 cohort passes preflight (admits the normal verdict path)
# ---------------------------------------------------------------------------


def test_R2B_pure_M6_cohort_passes_preflight() -> None:
    rng = np.random.default_rng(0xABCD)
    cells = [_m6_row(i, rng) for i in range(6)]
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    admissible = {"PASS", "FAIL", R2B_INDETERMINATE_VERDICT}
    assert verdict.verdict in admissible, (
        f"P0-2 VIOLATED: pure M6 cohort got verdict={verdict.verdict!r} "
        f"(expected one of {admissible}). Preflight is over-rejecting."
    )
    not_invalid_msg = (
        "P0-2 VIOLATED: pure M6 cohort should NOT trigger R2B_INVALID_NON_M6_PAYLOAD_VERDICT."
    )
    assert verdict.verdict != R2B_INVALID_NON_M6_PAYLOAD_VERDICT, not_invalid_msg


# ---------------------------------------------------------------------------
# Property 2: M1 row in M6 cohort → fail-closed; no statistics
# ---------------------------------------------------------------------------


def test_R2B_single_M1_row_in_cohort_fails_closed() -> None:
    rng = np.random.default_rng(0xBADD)
    cells: list[NullAuditCellPayload] = [_m6_row(i, rng) for i in range(5)]
    cells.append(_m1_row(99, rng))
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    assert verdict.verdict == R2B_INVALID_NON_M6_PAYLOAD_VERDICT, (
        f"P0-2 VIOLATED: M1 row injected → verdict={verdict.verdict!r}, "
        f"expected {R2B_INVALID_NON_M6_PAYLOAD_VERDICT!r}."
    )
    assert verdict.n_cells == 0, (
        f"P0-2 VIOLATED: invalid-payload verdict has n_cells={verdict.n_cells} "
        f"(expected 0; no statistics on invalid input)."
    )
    assert len(verdict.cell_results) == 0, (
        "P0-2 VIOLATED: invalid-payload verdict has non-empty cell_results "
        f"(len={len(verdict.cell_results)}; expected 0)."
    )


# ---------------------------------------------------------------------------
# Property 3: legacy default-strategy row → fail-closed
# ---------------------------------------------------------------------------


def test_R2B_legacy_default_strategy_row_fails_closed() -> None:
    rng = np.random.default_rng(0xC0DE)
    cells: list[NullAuditCellPayload] = [_legacy_row(i, rng) for i in range(3)]
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    assert verdict.verdict == R2B_INVALID_NON_M6_PAYLOAD_VERDICT, (
        f"P0-2 VIOLATED: legacy D002C_PAIRED_CRN_LEGACY cohort → "
        f"verdict={verdict.verdict!r}, expected "
        f"{R2B_INVALID_NON_M6_PAYLOAD_VERDICT!r}."
    )
    audit = verdict.metadata.get("r2b_provenance_audit", {})
    rejected = audit.get("rejected_rows", [])
    assert len(rejected) == len(cells), (
        f"P0-2 VIOLATED: legacy cohort should reject all rows; "
        f"audit rejected_rows={len(rejected)} of {len(cells)}."
    )


# ---------------------------------------------------------------------------
# Property 4: mixed M6 + M1 → fail-closed
# ---------------------------------------------------------------------------


def test_R2B_mixed_M6_and_M1_payload_fails_closed() -> None:
    rng = np.random.default_rng(0xDADA)
    cells: list[NullAuditCellPayload] = []
    for i in range(4):
        cells.append(_m6_row(i, rng))
        cells.append(_m1_row(100 + i, rng))
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    assert verdict.verdict == R2B_INVALID_NON_M6_PAYLOAD_VERDICT, (
        f"P0-2 VIOLATED: mixed M6+M1 cohort → verdict={verdict.verdict!r}, "
        f"expected {R2B_INVALID_NON_M6_PAYLOAD_VERDICT!r}."
    )
    audit = verdict.metadata.get("r2b_provenance_audit", {})
    rejected = audit.get("rejected_rows", [])
    # Half the rows are M1; preflight should flag at least all M1 rows.
    expected_min_rejected = sum(1 for c in cells if c.null_strategy != "M6_PLACEBO_COUPLING")
    assert len(rejected) >= expected_min_rejected, (
        f"P0-2 VIOLATED: mixed cohort under-rejected: rejected={len(rejected)} "
        f"< expected_min={expected_min_rejected}."
    )


# ---------------------------------------------------------------------------
# Property 5: aggregator NEVER stamps M6 on invalid input
# ---------------------------------------------------------------------------


def test_R2B_invalid_input_never_stamps_M6_provenance() -> None:
    """The R2BCellResult tuple must be empty on the invalid path.

    Pre-fix bug: the aggregator hard-coded
    ``null_strategy="M6_PLACEBO_COUPLING"`` on every emitted
    R2BCellResult, mislabelling provenance. With the preflight in place
    the invalid path returns ``cell_results=()`` — there is NO cell to
    mislabel.
    """
    rng = np.random.default_rng(0xEEEE)
    cells = [_legacy_row(i, rng) for i in range(3)] + [_m1_row(i, rng) for i in range(3)]
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    assert verdict.cell_results == (), (
        "P0-2 VIOLATED: aggregator emitted cell_results on invalid-payload "
        f"path: {verdict.cell_results!r}."
    )


# ---------------------------------------------------------------------------
# Property 6: invalid provenance NEVER yields PASS
# ---------------------------------------------------------------------------


def test_R2B_invalid_provenance_never_yields_pass() -> None:
    """Across an adversarial battery, no invalid-input cohort returns PASS."""
    rng = np.random.default_rng(0xF00D)
    cohorts: list[list[NullAuditCellPayload]] = [
        [_m1_row(i, rng) for i in range(4)],
        [_legacy_row(i, rng) for i in range(4)],
        [_m6_row(0, rng), _m1_row(1, rng), _m6_row(2, rng)],
        [_legacy_row(0, rng), _m6_row(1, rng), _m1_row(2, rng)],
    ]
    for k, cohort in enumerate(cohorts):
        verdict = evaluate_r2b(cohort, n_bootstrap=64, bca_seed=42)
        assert verdict.verdict != "PASS", (
            f"P0-2 VIOLATED: cohort {k} ({len(cohort)} rows) yielded PASS "
            "despite invalid M6 provenance. Aggregator MUST refuse."
        )
        invalid_msg = f"P0-2 VIOLATED: cohort {k} should be INVALID; got {verdict.verdict!r}."
        assert verdict.verdict == R2B_INVALID_NON_M6_PAYLOAD_VERDICT, invalid_msg
