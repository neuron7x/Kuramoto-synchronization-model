# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Strike R2 — M6 informativeness is CONDITIONAL on metric-topology coupling.

Attack
------
M6 preserves Frobenius norm of ΔK under random-site relocation. The
spectral structure is destroyed. A spectrally-driven metric will
discriminate the placebo; a topology-blind metric will not. R2-B PASS
is therefore NOT a verdict-grade certification unless the metric's
coupling-to-topology is explicitly measured per (substrate, metric).

This test:
  1. Constructs two synthetic placebo cell payloads:
     (a) ``spectrally_driven`` — null_values follow a distribution
         whose mean differs from precursor_values; M6 placebo lands
         far from the baseline, signal_over_ci >> 1, placebo-positive.
     (b) ``topology_blind`` — null_values and precursor_values are
         drawn from the SAME distribution (M6 indistinguishable from
         baseline); signal_over_ci ≈ 0, placebo-negative.
  2. Asserts that ``evaluate_r2b`` emits a per-cell
     ``topology_coupling_indicator`` in the capsule, and that the
     aggregate verdict downgrades to
     ``INDETERMINATE_R2B_TOPOLOGY_BLIND_METRIC`` when the indicator
     mean lies below the locked floor.

Phase-C repair surface
----------------------
``d002g_r2b_gate.py`` must:
  * Compute ``topology_coupling_indicator`` per cell (heuristic: the
    ratio of placebo-vs-baseline CI half-width to a reference scale).
  * Aggregate to an indicator mean.
  * If indicator mean < floor → verdict =
    ``INDETERMINATE_R2B_TOPOLOGY_BLIND_METRIC`` (NOT PASS, NOT FAIL).
"""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.d002c_sweep_runner import (
    PAYLOAD_SCHEMA_V2,
    NullAuditCellPayload,
)
from research.systemic_risk.d002g_r2b_gate import (
    R2B_INDETERMINATE_VERDICT,
    evaluate_r2b,
    r2b_verdict_to_capsule,
)

# Heavy statistical strike — gated behind `slow` so python-fast-tests stays
# under its 20-min cap; strike acceptor measurement_command runs without filter.
pytestmark = pytest.mark.slow


def _build_payload(
    *,
    cell_key: str,
    substrate_id: str,
    metric_id: str,
    N: int,
    lambda_: float,
    precursor: np.ndarray,
    null: np.ndarray,
) -> NullAuditCellPayload:
    """Build a NullAuditCellPayload with the v1 sha (legacy) discipline."""
    # We construct the dataclass directly; from_payload_dict requires a
    # pre-computed sha. Use the same canonical-JSON formula the writer uses.
    import hashlib
    import math

    from research.systemic_risk.d002c_preflight import canonical_preflight_json

    p_vals = tuple(float(x) for x in precursor)
    n_vals = tuple(float(x) for x in null)
    sha_input = {
        "cell_key": cell_key,
        "N": int(N),
        "lambda_": float(lambda_),
        "substrate_id": substrate_id,
        "metric_id": metric_id,
        "seed_ids": list(range(len(p_vals))),
        "precursor_values": list(p_vals),
        "null_values": list(n_vals),
        "paired_by_seed": True,
        "crn_identity_hash": "stub-r2-test-" + cell_key,
        "metric_version": "test_v1",
        "substrate_version": "test_v1",
    }
    sha = hashlib.sha256(canonical_preflight_json(sha_input).encode("utf-8")).hexdigest()
    _ = math  # keep import live without flake noise
    # P0-2 Codex review fix: R2-B aggregates ONLY M6 placebo payloads.
    # The R2 strike tests build M6-style cohorts by construction
    # (the "placebo" arm is the null leg). Mark the payload schema +
    # null_strategy explicitly so the new provenance preflight in
    # evaluate_r2b admits the row.
    return NullAuditCellPayload(
        cell_key=cell_key,
        N=int(N),
        lambda_=float(lambda_),
        substrate_id=substrate_id,
        metric_id=metric_id,
        seed_ids=tuple(range(len(p_vals))),
        precursor_values=p_vals,
        null_values=n_vals,
        paired_by_seed=True,
        crn_identity_hash="stub-r2-test-" + cell_key,
        metric_version="test_v1",
        substrate_version="test_v1",
        generated_at="",
        sha256=sha,
        payload_schema=PAYLOAD_SCHEMA_V2,
        null_strategy="M6_PLACEBO_COUPLING",
        null_seed=12345,
    )


def _make_spectrally_driven_cells(n_cells: int = 6) -> list[NullAuditCellPayload]:
    """Cells where M6 placebo is clearly discriminable (signal_over_ci > 1)."""
    rng = np.random.default_rng(0xDEAD)
    out: list[NullAuditCellPayload] = []
    for i in range(n_cells):
        # Strong signal: precursor mean = 1.0, null mean = 0.0, low noise.
        prec = rng.normal(loc=1.0, scale=0.05, size=20)
        nul = rng.normal(loc=0.0, scale=0.05, size=20)
        out.append(
            _build_payload(
                cell_key=f"spec_{i}",
                substrate_id="ricci_flow",
                metric_id="sync_auc",
                N=50,
                lambda_=0.5,
                precursor=prec,
                null=nul,
            )
        )
    return out


def _make_topology_blind_cells(n_cells: int = 6) -> list[NullAuditCellPayload]:
    """Cells where M6 placebo is indistinguishable from baseline (s.o.c. ≈ 0)."""
    rng = np.random.default_rng(0xBEEF)
    out: list[NullAuditCellPayload] = []
    for i in range(n_cells):
        # Both arms drawn from the same distribution → mean diff ≈ 0,
        # CI half-width >> mean diff → signal_over_ci << 1.
        prec = rng.normal(loc=0.0, scale=1.0, size=20)
        nul = rng.normal(loc=0.0, scale=1.0, size=20)
        out.append(
            _build_payload(
                cell_key=f"blind_{i}",
                substrate_id="ricci_flow",
                metric_id="topology_blind_metric",
                N=50,
                lambda_=0.5,
                precursor=prec,
                null=nul,
            )
        )
    return out


def test_R2_capsule_emits_topology_coupling_indicator() -> None:
    """R2-B capsule MUST include a per-cell topology_coupling_indicator field."""
    cells = _make_spectrally_driven_cells()
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    cap = r2b_verdict_to_capsule(verdict)
    has_mean = "topology_coupling_indicator_mean" in cap
    assert has_mean, "R2 VIOLATED: capsule missing topology_coupling_indicator_mean"
    # Per-cell indicator also exposed
    cell_rows = cap["cell_results"]
    for row in cell_rows:
        has_indicator = "topology_coupling_indicator" in row
        msg = f"R2 VIOLATED: per-cell row {row['cell_key']!r} missing coupling indicator"
        assert has_indicator, msg


def test_R2_topology_blind_metric_downgrades_to_indeterminate() -> None:
    """If the metric is topology-blind, R2-B must NOT return PASS or FAIL.

    Verdict must be ``R2B_INDETERMINATE_VERDICT`` per the conditional-
    informativeness rule.
    """
    cells = _make_topology_blind_cells()
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    assert verdict.verdict == R2B_INDETERMINATE_VERDICT, (
        f"R2 VIOLATED: topology-blind cohort got verdict={verdict.verdict!r} "
        f"(coupling_indicator_mean={verdict.topology_coupling_indicator_mean:.3e}). "
        f"Expected {R2B_INDETERMINATE_VERDICT!r}."
    )


def test_R2_spectrally_driven_metric_does_not_downgrade() -> None:
    """A spectrally-driven cohort with strong signal must NOT trigger
    INDETERMINATE — the verdict should resolve to PASS or FAIL normally."""
    cells = _make_spectrally_driven_cells()
    verdict = evaluate_r2b(cells, n_bootstrap=64, bca_seed=42)
    assert verdict.verdict in {"PASS", "FAIL"}, (
        f"R2 VIOLATED: spectrally-driven cohort got verdict={verdict.verdict!r}. "
        "INDETERMINATE should fire only when the metric is topology-blind."
    )
