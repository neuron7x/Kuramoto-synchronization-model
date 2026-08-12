# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic synthetic tests for the Physics v2 manifold contracts.

These are the first-slice acceptance witnesses required by the architecture
handoff (§7 item 4): timestamp monotonicity, hash/replay determinism, no-look-
ahead construction, and the fail-closed DATA_UNAVAILABLE behaviour that proves a
missing licensed-L2 dataset is *explicit*, never silently replaced with
synthetic data.

The literal-free determinism / fail-closed tests are bound as ``@law`` witnesses
to the candidate (warn-severity) Physics v2 laws. They carry no magic numeric
literals, so they pass ``tools/validate_tests.py`` cleanly while lifting law
coverage. The bounds tests that need numeric inputs are left as plain pytest
tests (orphans to the law validator, by design).
"""

from __future__ import annotations

import pytest

from physics_contracts import law, load_catalog
from physics_contracts.manifold import fixtures as fx
from physics_contracts.manifold.contracts import (
    CausalCutoffStatus,
    ComparisonReport,
    CurvatureSyncFrame,
    EvidenceCapsuleShape,
    LicensedDataStatus,
    LicensedDataUnavailable,
    MarketCausalGraphSnapshot,
    NullControl,
    deterministic_run_id,
    require_licensed_l2,
    resolve_data_status,
)

CANDIDATE_LAW_IDS = (
    "manifold.metric_snapshot_schema",
    "manifold.causal_cutoff",
    "manifold.provenance_replay_identity",
    "manifold.curvature_transport_balance",
    "ricci.flow_energy_nonincrease_declared_domain",
    "kuramoto.finite_size_scaling_with_causal_cutoff",
)


# --------------------------------------------------------------------------- #
# Catalog wiring                                                              #
# --------------------------------------------------------------------------- #
def test_candidate_laws_present_and_warn_severity() -> None:
    catalog = load_catalog()
    for law_id in CANDIDATE_LAW_IDS:
        assert law_id in catalog, f"missing candidate law {law_id}"
        assert catalog[law_id].severity == "warn", (
            f"{law_id} must be non-blocking (warn) in this first slice; "
            f"got {catalog[law_id].severity}"
        )


# --------------------------------------------------------------------------- #
# Replay identity (literal-free witnesses)                                    #
# --------------------------------------------------------------------------- #
@law("manifold.provenance_replay_identity")
def test_snapshot_id_is_deterministic() -> None:
    a = fx.synthetic_snapshot()
    b = fx.synthetic_snapshot()
    assert a == b
    assert a.snapshot_id == b.snapshot_id


@law("manifold.provenance_replay_identity")
def test_distinct_seeds_yield_distinct_snapshot_ids() -> None:
    first = fx.synthetic_snapshot(seed=1)
    second = fx.synthetic_snapshot(seed=2)
    assert first.snapshot_id != second.snapshot_id


@law("manifold.provenance_replay_identity")
def test_run_id_is_deterministic_function_of_provenance() -> None:
    left = deterministic_run_id("cfg", "fingerprint", "commit")
    right = deterministic_run_id("cfg", "fingerprint", "commit")
    assert left == right
    assert left != deterministic_run_id("cfg", "fingerprint", "other-commit")


@law("manifold.provenance_replay_identity")
def test_run_id_rejects_empty_provenance() -> None:
    with pytest.raises(ValueError):
        deterministic_run_id("", "fingerprint", "commit")


@law("manifold.provenance_replay_identity")
def test_capsule_digest_is_deterministic() -> None:
    assert fx.synthetic_capsule().capsule_digest == fx.synthetic_capsule().capsule_digest


@law("manifold.provenance_replay_identity")
def test_comparison_report_digest_is_deterministic() -> None:
    assert (
        fx.synthetic_comparison_report().report_digest
        == fx.synthetic_comparison_report().report_digest
    )


# --------------------------------------------------------------------------- #
# Snapshot schema + causal cutoff (literal-free witnesses)                    #
# --------------------------------------------------------------------------- #
@law("manifold.metric_snapshot_schema")
def test_synthetic_snapshot_is_well_formed() -> None:
    snapshot = fx.synthetic_snapshot()
    assert len(snapshot.edges) == len(snapshot.edge_weights)
    assert len(set(snapshot.nodes)) == len(snapshot.nodes)


@law("manifold.metric_snapshot_schema")
def test_non_monotonic_interval_fails_closed() -> None:
    base = fx.synthetic_snapshot()
    with pytest.raises(ValueError):
        MarketCausalGraphSnapshot(
            timestamp_start=base.timestamp_end,
            timestamp_end=base.timestamp_start,
            nodes=base.nodes,
            edges=base.edges,
            edge_weights=base.edge_weights,
            latency_floor_seconds=base.latency_floor_seconds,
            causal_cutoff_seconds=base.causal_cutoff_seconds,
            dataset_fingerprint=base.dataset_fingerprint,
            construction_config_hash=base.construction_config_hash,
            builder_method=base.builder_method,
        )


@law("manifold.causal_cutoff")
def test_no_lookahead_accepts_past_events() -> None:
    snapshot = fx.synthetic_snapshot()
    snapshot.assert_no_lookahead((snapshot.timestamp_start, snapshot.timestamp_end))


@law("manifold.causal_cutoff")
def test_no_lookahead_rejects_future_event() -> None:
    snapshot = fx.synthetic_snapshot()
    future = snapshot.timestamp_end + snapshot.causal_cutoff_seconds
    with pytest.raises(ValueError):
        snapshot.assert_no_lookahead((future,))


# --------------------------------------------------------------------------- #
# Fail-closed licensed-data gate (literal-free witnesses)                     #
# --------------------------------------------------------------------------- #
@law("manifold.causal_cutoff")
def test_require_licensed_l2_fails_closed_on_missing_data() -> None:
    with pytest.raises(LicensedDataUnavailable):
        require_licensed_l2(None)


@law("manifold.causal_cutoff")
def test_require_licensed_l2_rejects_synthetic_fingerprint() -> None:
    synthetic_fp = fx.synthetic_snapshot().dataset_fingerprint
    assert resolve_data_status(synthetic_fp) is LicensedDataStatus.DATA_UNAVAILABLE
    with pytest.raises(LicensedDataUnavailable):
        require_licensed_l2(synthetic_fp)


@law("manifold.causal_cutoff")
def test_require_licensed_l2_passes_real_fingerprint_through() -> None:
    real_fp = "a" * 64
    assert resolve_data_status(real_fp) is LicensedDataStatus.AVAILABLE
    assert require_licensed_l2(real_fp) == real_fp


@law("manifold.provenance_replay_identity")
def test_capsule_blocks_real_maturity_without_data() -> None:
    with pytest.raises(ValueError):
        EvidenceCapsuleShape(
            run_id="r",
            dataset_fingerprint="synthetic:1",
            config_hash="c",
            code_commit="x",
            laws_exercised=("manifold.metric_snapshot_schema",),
            falsifiers_passed=(),
            falsifiers_failed=(),
            comparison_report_digest="d",
            claim_maturity="BOUNDED_CLAIM_ALLOWED",
            data_status=LicensedDataStatus.DATA_UNAVAILABLE,
        )


# --------------------------------------------------------------------------- #
# Comparison report downgrade discipline (plain tests — numeric inputs)        #
# --------------------------------------------------------------------------- #
def test_comparison_report_survival_requires_beating_every_control() -> None:
    # Candidate ties a control: SURVIVED_NULLS is illegal, must fail closed.
    with pytest.raises(ValueError):
        ComparisonReport(
            candidate_statistic=0.5,
            null_controls=(
                NullControl(name="shuffled_timestamp", statistic=0.5),
                NullControl(name="rewire", statistic=0.1),
            ),
            claim_status="SURVIVED_NULLS",
            validity_domain="unit-test",
        )


def test_comparison_report_artifact_suspected_is_always_legal() -> None:
    report = fx.synthetic_comparison_report(survives=False)
    assert report.claim_status == "ARTIFACT_SUSPECTED"
    assert report.survives_all_controls is False


def test_comparison_report_survives_when_candidate_dominates() -> None:
    report = fx.synthetic_comparison_report(survives=True)
    assert report.claim_status == "SURVIVED_NULLS"
    assert report.survives_all_controls is True


# --------------------------------------------------------------------------- #
# Snapshot bounds (plain tests — numeric inputs)                              #
# --------------------------------------------------------------------------- #
def test_negative_latency_rejected() -> None:
    with pytest.raises(ValueError):
        MarketCausalGraphSnapshot(
            timestamp_start=0.0,
            timestamp_end=1.0,
            nodes=("a", "b"),
            edges=((0, 1),),
            edge_weights=(0.5,),
            latency_floor_seconds=-0.1,
            causal_cutoff_seconds=0.2,
            dataset_fingerprint="fp",
            construction_config_hash="cfg",
            builder_method="test",
        )


def test_cutoff_below_latency_floor_rejected() -> None:
    with pytest.raises(ValueError):
        MarketCausalGraphSnapshot(
            timestamp_start=0.0,
            timestamp_end=1.0,
            nodes=("a", "b"),
            edges=((0, 1),),
            edge_weights=(0.5,),
            latency_floor_seconds=0.3,
            causal_cutoff_seconds=0.1,
            dataset_fingerprint="fp",
            construction_config_hash="cfg",
            builder_method="test",
        )


def test_edge_index_out_of_range_rejected() -> None:
    with pytest.raises(ValueError):
        MarketCausalGraphSnapshot(
            timestamp_start=0.0,
            timestamp_end=1.0,
            nodes=("a", "b"),
            edges=((0, 5),),
            edge_weights=(0.5,),
            latency_floor_seconds=0.1,
            causal_cutoff_seconds=0.2,
            dataset_fingerprint="fp",
            construction_config_hash="cfg",
            builder_method="test",
        )


def test_negative_edge_weight_rejected() -> None:
    with pytest.raises(ValueError):
        MarketCausalGraphSnapshot(
            timestamp_start=0.0,
            timestamp_end=1.0,
            nodes=("a", "b"),
            edges=((0, 1),),
            edge_weights=(-0.5,),
            latency_floor_seconds=0.1,
            causal_cutoff_seconds=0.2,
            dataset_fingerprint="fp",
            construction_config_hash="cfg",
            builder_method="test",
        )


def test_sync_frame_order_parameter_must_be_bounded() -> None:
    with pytest.raises(ValueError):
        CurvatureSyncFrame(
            snapshot_id="sid",
            order_parameter=1.5,
            phase_dispersion=0.1,
            mean_curvature=0.0,
            causal_cutoff_status=CausalCutoffStatus.VALID,
            finite_size_floor=0.1,
            regime_label="subcritical",
            validity_domain="unit-test",
        )


def test_sync_frame_rejects_unknown_regime_label() -> None:
    with pytest.raises(ValueError):
        CurvatureSyncFrame(
            snapshot_id="sid",
            order_parameter=0.3,
            phase_dispersion=0.1,
            mean_curvature=0.0,
            causal_cutoff_status=CausalCutoffStatus.VALID,
            finite_size_floor=0.1,
            regime_label="moon-phase",
            validity_domain="unit-test",
        )


def test_synthetic_sync_frame_round_trips() -> None:
    frame = fx.synthetic_sync_frame(seed=2)
    assert 0.0 <= frame.order_parameter <= 1.0
    assert frame.regime_label in {"subcritical", "supercritical", "critical", "chimera", "unknown"}
