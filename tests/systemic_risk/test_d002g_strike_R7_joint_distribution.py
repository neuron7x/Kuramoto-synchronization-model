# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Strike R7 — joint distribution of (R1 ∧ R2 ∧ R3 ∧ R2-B) is uncharacterised.

Attack
------
R1, R2, R3 and R2-B all depend on ``signal_over_ci``. Treating them as
independent rules under multi-test correction is wrong when they share
a common metric statistic. The capsule must expose the empirical rule
correlation matrix so the consumer can assess.

This test asserts the R2-B capsule carries a
``rule_correlation_matrix`` block:

  * square (k × k for k rule statistics),
  * diagonal entries == 1.0,
  * no NaN / Inf,
  * off-diagonal entries reported (any finite value in [-1, 1] is OK,
    we only test well-formedness).

The k rule statistics we expose are:
  - signal_over_ci
  - topology_coupling_indicator
  - signal_mean
  - bca_ci_half_width

Phase-C repair surface: ``r2b_verdict_to_capsule`` now emits
``rule_correlation_matrix`` (a list-of-lists JSON-pure float matrix)
and the corresponding ``rule_correlation_labels`` list.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from research.systemic_risk.d002c_preflight import canonical_preflight_json
from research.systemic_risk.d002c_sweep_runner import (
    PAYLOAD_SCHEMA_V2,
    NullAuditCellPayload,
)
from research.systemic_risk.d002g_r2b_gate import (
    evaluate_r2b,
    r2b_verdict_to_capsule,
)

# Joint rule-correlation matrix synthesis — gate behind `slow`.
pytestmark = pytest.mark.slow


def _build_payload(
    *,
    cell_key: str,
    precursor: np.ndarray,
    null: np.ndarray,
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
        "crn_identity_hash": "stub-r7-" + cell_key,
        "metric_version": "test_v1",
        "substrate_version": "test_v1",
    }
    sha = hashlib.sha256(canonical_preflight_json(sha_input).encode("utf-8")).hexdigest()
    # P0-2 Codex review fix: M6 provenance required by evaluate_r2b.
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
        crn_identity_hash="stub-r7-" + cell_key,
        metric_version="test_v1",
        substrate_version="test_v1",
        generated_at="",
        sha256=sha,
        payload_schema=PAYLOAD_SCHEMA_V2,
        null_strategy="M6_PLACEBO_COUPLING",
        null_seed=99999,
    )


def _make_cells_with_shared_inflation(n_cells: int = 8) -> list[NullAuditCellPayload]:
    """Build cells whose signal_over_ci is correlated by construction.

    For each cell, draw a per-cell scale factor and apply it to the
    precursor arm. This induces correlation between signal_mean and
    signal_over_ci across cells.
    """
    rng = np.random.default_rng(0xC0FFEE)
    cells: list[NullAuditCellPayload] = []
    for i in range(n_cells):
        scale = float(0.5 + 0.5 * (i % 4))  # 0.5, 1.0, 1.5, 2.0 cycle
        prec = rng.normal(loc=scale, scale=0.1, size=20)
        nul = rng.normal(loc=0.0, scale=0.1, size=20)
        cells.append(_build_payload(cell_key=f"r7_{i}", precursor=prec, null=nul))
    return cells


def test_R7_capsule_emits_rule_correlation_matrix() -> None:
    cells = _make_cells_with_shared_inflation()
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    cap = r2b_verdict_to_capsule(verdict)
    has_mat = "rule_correlation_matrix" in cap
    assert has_mat, "R7 VIOLATED: r2b capsule missing 'rule_correlation_matrix'"
    has_labels = "rule_correlation_labels" in cap
    assert has_labels, "R7 VIOLATED: r2b capsule missing 'rule_correlation_labels'"
    labels = list(cap["rule_correlation_labels"])
    mat = cap["rule_correlation_matrix"]
    k = len(labels)
    assert k >= 2, f"R7 VIOLATED: need ≥2 rule stats, got {labels}"
    assert len(mat) == k, f"R7 VIOLATED: correlation matrix rows {len(mat)} ≠ k {k}"
    for i, row in enumerate(mat):
        assert len(row) == k, f"R7 VIOLATED: row {i} length {len(row)} ≠ k {k}"
        for j, v in enumerate(row):
            fv = float(v)
            finite = bool(np.isfinite(fv))
            msg_f = f"R7 VIOLATED: correlation_matrix[{i}][{j}] = {fv!r} (not finite)"
            assert finite, msg_f
            in_band = -1.0 - 1e-9 <= fv <= 1.0 + 1e-9
            msg_b = f"R7 VIOLATED: correlation_matrix[{i}][{j}] = {fv} outside [-1, 1]"
            assert in_band, msg_b
        # Diagonal == 1 (within tiny float tolerance)
        diag_ok = abs(float(row[i]) - 1.0) < 1e-9
        msg_d = f"R7 VIOLATED: correlation_matrix diagonal [{i}][{i}] = {row[i]} ≠ 1"
        assert diag_ok, msg_d
