# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""R2-B capsule schema contract test.

Required fields:
  * ``capsule_version == 'd002g_r2b_capsule_v1'``
  * ``verdict ∈ {'PASS', 'FAIL', R2B_INDETERMINATE_VERDICT}``
  * ``FPR_R2B`` (float, in [0, 1])
  * ``threshold`` (locked at 0.05)
  * ``bonferroni_n_cells == 216`` (prereg)
  * ``bonferroni_alpha_per_cell == 0.05 / 216``
  * ``sha256`` 64-hex
  * per-cell breakdown carries
    ``{cell_key, substrate_id, metric_id, N, lambda_, n_seeds,
       signal_mean, bca_ci_lo, bca_ci_hi, signal_over_ci,
       is_placebo_positive, null_strategy, topology_coupling_indicator}``
  * top-level ``topology_coupling_indicator_mean`` and
    ``topology_coupling_floor`` carried (Strike-R2)
  * top-level ``rule_correlation_matrix`` + ``rule_correlation_labels``
    carried (Strike-R7)
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

from research.systemic_risk.d002c_preflight import canonical_preflight_json
from research.systemic_risk.d002c_sweep_runner import (
    PAYLOAD_SCHEMA_V2,
    NullAuditCellPayload,
)
from research.systemic_risk.d002g_r2b_gate import (
    R2B_BONFERRONI_N_CELLS,
    R2B_CAPSULE_VERSION,
    R2B_FPR_THRESHOLD,
    R2B_INDETERMINATE_VERDICT,
    evaluate_r2b,
    r2b_verdict_to_capsule,
)


def _make_cell(i: int, rng: np.random.Generator) -> NullAuditCellPayload:
    prec = rng.normal(loc=1.0, scale=0.1, size=20)
    nul = rng.normal(loc=0.0, scale=0.1, size=20)
    sha_input = {
        "cell_key": f"cap_{i}",
        "N": 50,
        "lambda_": 0.5,
        "substrate_id": "ricci_flow",
        "metric_id": "sync_auc",
        "seed_ids": list(range(20)),
        "precursor_values": [float(x) for x in prec],
        "null_values": [float(x) for x in nul],
        "paired_by_seed": True,
        "crn_identity_hash": f"capshahash{i}",
        "metric_version": "v1",
        "substrate_version": "v1",
    }
    sha = hashlib.sha256(canonical_preflight_json(sha_input).encode("utf-8")).hexdigest()
    # P0-2 Codex review fix: R2-B aggregator now requires M6 provenance.
    # These capsule-schema cells represent an M6 cohort by intent.
    return NullAuditCellPayload(
        cell_key=f"cap_{i}",
        N=50,
        lambda_=0.5,
        substrate_id="ricci_flow",
        metric_id="sync_auc",
        seed_ids=tuple(range(20)),
        precursor_values=tuple(float(x) for x in prec),
        null_values=tuple(float(x) for x in nul),
        paired_by_seed=True,
        crn_identity_hash=f"capshahash{i}",
        metric_version="v1",
        substrate_version="v1",
        generated_at="",
        sha256=sha,
        payload_schema=PAYLOAD_SCHEMA_V2,
        null_strategy="M6_PLACEBO_COUPLING",
        null_seed=12345 + i,
    )


def test_r2b_capsule_has_required_top_level_fields() -> None:
    rng = np.random.default_rng(0)
    cells = [_make_cell(i, rng) for i in range(6)]
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    cap = r2b_verdict_to_capsule(verdict)
    expected_fields = {
        "capsule_version",
        "verdict",
        "fpr_r2b",
        "threshold",
        "n_cells",
        "n_placebo_positive",
        "bonferroni_n_cells",
        "bonferroni_alpha_per_cell",
        "ci_alpha",
        "topology_coupling_indicator_mean",
        "topology_coupling_floor",
        "rule_correlation_matrix",
        "rule_correlation_labels",
        "cell_results",
        "sha256",
    }
    missing = expected_fields - set(cap.keys())
    assert not missing, f"r2b capsule missing fields {missing}; got {sorted(cap)}"
    assert cap["capsule_version"] == R2B_CAPSULE_VERSION
    assert cap["bonferroni_n_cells"] == R2B_BONFERRONI_N_CELLS
    # Bonferroni alpha per-cell == 0.05/216
    expected_alpha = R2B_FPR_THRESHOLD / R2B_BONFERRONI_N_CELLS
    assert abs(float(cap["bonferroni_alpha_per_cell"]) - expected_alpha) < 1e-15
    assert cap["verdict"] in {"PASS", "FAIL", R2B_INDETERMINATE_VERDICT}
    assert re.fullmatch(r"[0-9a-f]{64}", cap["sha256"])


def test_r2b_capsule_per_cell_carries_all_fields() -> None:
    rng = np.random.default_rng(1)
    cells = [_make_cell(i, rng) for i in range(4)]
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    cap = r2b_verdict_to_capsule(verdict)
    expected_cell_fields = {
        "cell_key",
        "substrate_id",
        "metric_id",
        "N",
        "lambda_",
        "n_seeds",
        "signal_mean",
        "bca_ci_lo",
        "bca_ci_hi",
        "signal_over_ci",
        "is_placebo_positive",
        "null_strategy",
        "topology_coupling_indicator",
    }
    for row in cap["cell_results"]:
        missing = expected_cell_fields - set(row.keys())
        assert not missing, f"cell row missing {missing}; row={sorted(row)}"


def test_r2b_capsule_fpr_in_unit_interval() -> None:
    rng = np.random.default_rng(2)
    cells = [_make_cell(i, rng) for i in range(8)]
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    cap = r2b_verdict_to_capsule(verdict)
    fpr = float(cap["fpr_r2b"])
    assert 0.0 <= fpr <= 1.0, f"FPR_R2B = {fpr} outside [0, 1]"
