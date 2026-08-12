# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic synthetic fixtures for the Physics v2 manifold contracts.

These builders are **pure functions of an integer seed** — no RNG, no clock, no
I/O. The same seed always yields byte-identical objects, which is what the
synthetic-test deliverable (architecture doc §7 item 4) and the replay-identity
law require.

Every synthetic snapshot carries a ``dataset_fingerprint`` tagged with
``SYNTHETIC_FINGERPRINT_PREFIX`` so that ``require_licensed_l2`` will *reject* it
in a real-data path: a fixture can never be mistaken for licensed L2 data.
"""

from __future__ import annotations

from physics_contracts.manifold.contracts import (
    SYNTHETIC_FINGERPRINT_PREFIX,
    CausalCutoffStatus,
    ComparisonReport,
    CurvatureSyncFrame,
    EvidenceCapsuleShape,
    LicensedDataStatus,
    MarketCausalGraphSnapshot,
    NullControl,
    canonical_digest,
    deterministic_run_id,
)


def synthetic_fingerprint(seed: int) -> str:
    """A clearly-synthetic, deterministic fingerprint for a given seed."""

    return f"{SYNTHETIC_FINGERPRINT_PREFIX}{seed:08d}"


def synthetic_snapshot(seed: int = 0, n_nodes: int = 4) -> MarketCausalGraphSnapshot:
    """Build a deterministic ring-graph snapshot from ``seed``.

    The construction is fully closed-form: node ids, a directed ring of edges,
    and weights derived arithmetically from the seed. No randomness is involved,
    so two calls with the same arguments return equal snapshots with identical
    ``snapshot_id``.
    """

    if n_nodes < 2:
        raise ValueError("synthetic_snapshot requires n_nodes >= 2")
    nodes = tuple(f"node_{i}" for i in range(n_nodes))
    edges = tuple((i, (i + 1) % n_nodes) for i in range(n_nodes))
    # Deterministic, finite, non-negative weights in (0, 1].
    edge_weights = tuple(((seed + i + 1) % 7 + 1) / 8.0 for i in range(n_nodes))
    config_hash = canonical_digest({"builder": "synthetic_ring", "seed": seed, "n_nodes": n_nodes})
    return MarketCausalGraphSnapshot(
        timestamp_start=float(seed),
        timestamp_end=float(seed) + 1.0,
        nodes=nodes,
        edges=edges,
        edge_weights=edge_weights,
        latency_floor_seconds=0.1,
        causal_cutoff_seconds=0.25,
        dataset_fingerprint=synthetic_fingerprint(seed),
        construction_config_hash=config_hash,
        builder_method="synthetic_ring",
    )


def synthetic_sync_frame(seed: int = 0) -> CurvatureSyncFrame:
    """Build a deterministic curvature/synchronization frame schema instance."""

    snapshot = synthetic_snapshot(seed)
    # Closed-form, bounded descriptors. order_parameter stays within [0, 1].
    order_parameter = ((seed % 5) + 1) / 10.0
    return CurvatureSyncFrame(
        snapshot_id=snapshot.snapshot_id,
        order_parameter=order_parameter,
        phase_dispersion=1.0 - order_parameter,
        mean_curvature=((seed % 3) - 1) / 2.0,
        causal_cutoff_status=CausalCutoffStatus.VALID,
        finite_size_floor=3.0 / (len(snapshot.nodes) ** 0.5),
        regime_label="subcritical",
        validity_domain="synthetic-fixture; no market claim",
    )


def synthetic_comparison_report(seed: int = 0, *, survives: bool = False) -> ComparisonReport:
    """Build a deterministic comparison report.

    When ``survives`` is False the four null controls bracket the candidate so the
    only legal status is ``ARTIFACT_SUSPECTED``; when True the candidate strictly
    beats every control and ``SURVIVED_NULLS`` is legal.
    """

    base = (seed % 4) / 10.0
    candidate = base + (0.5 if survives else 0.0)
    controls = (
        NullControl(name="shuffled_timestamp", statistic=base + (0.0 if survives else 0.1)),
        NullControl(name="shuffled_causal_direction", statistic=base + (0.01 if survives else 0.2)),
        NullControl(name="degree_preserving_rewire", statistic=base + (0.02 if survives else 0.15)),
        NullControl(name="causal_cutoff_violation", statistic=base + (0.03 if survives else 0.25)),
    )
    status = "SURVIVED_NULLS" if survives else "ARTIFACT_SUSPECTED"
    return ComparisonReport(
        candidate_statistic=candidate,
        null_controls=controls,
        claim_status=status,
        validity_domain="synthetic-fixture; no market claim",
    )


def synthetic_capsule(seed: int = 0) -> EvidenceCapsuleShape:
    """Build a deterministic, synthetic-tier evidence capsule shape.

    Because the dataset is synthetic, the capsule's ``data_status`` is
    ``DATA_UNAVAILABLE`` and its ``claim_maturity`` stays at a synthetic-or-lower
    tier — the fail-closed rule forbids any real-data maturity here.
    """

    fingerprint = synthetic_fingerprint(seed)
    config_hash = canonical_digest({"capsule": "synthetic", "seed": seed})
    code_commit = "synthetic-commit"
    report = synthetic_comparison_report(seed)
    return EvidenceCapsuleShape(
        run_id=deterministic_run_id(config_hash, fingerprint, code_commit),
        dataset_fingerprint=fingerprint,
        config_hash=config_hash,
        code_commit=code_commit,
        laws_exercised=(
            "manifold.metric_snapshot_schema",
            "manifold.provenance_replay_identity",
        ),
        falsifiers_passed=("synthetic_timestamp_monotonicity", "synthetic_no_lookahead"),
        falsifiers_failed=(),
        comparison_report_digest=report.report_digest,
        claim_maturity="MEASURED_SYNTHETIC",
        data_status=LicensedDataStatus.DATA_UNAVAILABLE,
    )
