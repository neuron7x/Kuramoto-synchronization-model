# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Replication capsule — comparator tests (pillar 6)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from research.systemic_risk.replication import RunManifest
from research.systemic_risk.replication_capsule import (
    DEFAULT_BIT_IDENTICAL_TOLERANCE,
    DEFAULT_DETERMINISTIC_TOLERANCE,
    ReplicationOutcome,
    compare_run_outputs,
    manifest_replication_sha,
)


def _make_manifest(
    *,
    seed: int = 42,
    config_hash: str = "a" * 64,
    commit_sha: str = "deadbeef",
    config: dict[str, Any] | None = None,
) -> RunManifest:
    return RunManifest(
        commit_sha=commit_sha,
        git_dirty=False,
        timestamp_utc="2026-05-08T14:00:00+00:00",
        seed=seed,
        config_hash=config_hash,
        python="3.12.0",
        platform_info="Linux",
        package_versions={"numpy": "2.0.0"},
        config=config if config is not None else {"alpha": 0.05},
        extra={},
    )


class TestManifestReplicationSha:
    def test_returns_64_hex(self) -> None:
        m = _make_manifest()
        sha = manifest_replication_sha(m)
        assert isinstance(sha, str)
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)

    def test_idempotent(self) -> None:
        m = _make_manifest()
        assert manifest_replication_sha(m) == manifest_replication_sha(m)

    def test_different_manifests_different_shas(self) -> None:
        a = _make_manifest(seed=1)
        b = _make_manifest(seed=2)
        assert manifest_replication_sha(a) != manifest_replication_sha(b)


class TestCompareBitIdentical:
    def test_exact_match_passes(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=0.85,
            tolerance_class="bit_identical",
        )
        assert isinstance(out, ReplicationOutcome)
        assert out.matched
        assert out.reason == "matched"
        assert out.tolerance == DEFAULT_BIT_IDENTICAL_TOLERANCE
        assert out.deviation == 0.0

    def test_one_ulp_drift_caught(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=0.85 + 1e-15,
            tolerance_class="bit_identical",
        )
        assert not out.matched
        assert out.reason == "metric_deviation_exceeds_tolerance"


class TestCompareDeterministicWithDrift:
    def test_within_default_tol_passes(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=0.85 + 1e-13,
            tolerance_class="deterministic_with_drift",
        )
        assert out.matched
        assert out.tolerance == DEFAULT_DETERMINISTIC_TOLERANCE

    def test_outside_default_tol_caught(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=0.85 + 1e-10,
            tolerance_class="deterministic_with_drift",
        )
        assert not out.matched
        assert out.reason == "metric_deviation_exceeds_tolerance"


class TestCompareStochasticSeeded:
    def test_requires_explicit_tolerance(self) -> None:
        m = _make_manifest()
        with pytest.raises(ValueError, match="explicit tolerance_override"):
            compare_run_outputs(
                primary_manifest=m,
                secondary_manifest=m,
                primary_metric=0.85,
                secondary_metric=0.85,
                tolerance_class="stochastic_seeded",
            )

    def test_within_explicit_tol_passes(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=0.853,
            tolerance_class="stochastic_seeded",
            tolerance_override=5e-3,
        )
        assert out.matched

    def test_outside_explicit_tol_caught(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=0.81,
            tolerance_class="stochastic_seeded",
            tolerance_override=5e-3,
        )
        assert not out.matched
        assert out.deviation == pytest.approx(0.04)


class TestContractGuards:
    def test_negative_tolerance_caught(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=0.85,
            tolerance_class="bit_identical",
            tolerance_override=-1.0,
        )
        assert not out.matched
        assert out.reason == "tolerance_negative"

    def test_nan_primary_metric_caught(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=math.nan,
            secondary_metric=0.85,
            tolerance_class="bit_identical",
        )
        assert not out.matched
        assert out.reason == "non_finite_primary_metric"

    def test_inf_secondary_metric_caught(self) -> None:
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=math.inf,
            tolerance_class="bit_identical",
        )
        assert not out.matched
        assert out.reason == "non_finite_secondary_metric"

    def test_config_hash_divergence_caught(self) -> None:
        primary = _make_manifest(config_hash="a" * 64)
        secondary = _make_manifest(config_hash="b" * 64)
        out = compare_run_outputs(
            primary_manifest=primary,
            secondary_manifest=secondary,
            primary_metric=0.85,
            secondary_metric=0.85,
            tolerance_class="bit_identical",
        )
        assert not out.matched
        assert out.reason == "config_hash_diverged"

    def test_seed_divergence_caught(self) -> None:
        primary = _make_manifest(seed=1)
        secondary = _make_manifest(seed=2)
        out = compare_run_outputs(
            primary_manifest=primary,
            secondary_manifest=secondary,
            primary_metric=0.85,
            secondary_metric=0.85,
            tolerance_class="bit_identical",
        )
        assert not out.matched
        assert out.reason == "seed_diverged"


class TestProtocolCompatibility:
    def test_outcome_matches_replication_result_like(self) -> None:
        """The outcome's ``matched`` field is the contract surface
        consumed by ``death_conditions.trigger_replication_mismatch``."""
        m = _make_manifest()
        out = compare_run_outputs(
            primary_manifest=m,
            secondary_manifest=m,
            primary_metric=0.85,
            secondary_metric=0.85,
            tolerance_class="bit_identical",
        )
        assert hasattr(out, "matched")
        assert isinstance(out.matched, bool)

    def test_mismatch_drives_kill_via_death_engine(self) -> None:
        from research.systemic_risk.death_conditions import (
            ReplicationResultLike,
            trigger_replication_mismatch,
        )

        primary = _make_manifest(seed=1)
        secondary = _make_manifest(seed=2)
        out = compare_run_outputs(
            primary_manifest=primary,
            secondary_manifest=secondary,
            primary_metric=0.85,
            secondary_metric=0.85,
            tolerance_class="bit_identical",
        )
        # Wrap the frozen ReplicationOutcome in a settable-attribute holder
        # to satisfy the structural ReplicationResultLike protocol (whose
        # `matched` field mypy treats as a settable variable).
        from dataclasses import dataclass as _dc

        @_dc
        class _LikeShim:
            matched: bool

        shim: ReplicationResultLike = _LikeShim(matched=out.matched)
        trigger_outcome = trigger_replication_mismatch(shim)
        assert trigger_outcome.fired
        assert trigger_outcome.action == "KILL"
