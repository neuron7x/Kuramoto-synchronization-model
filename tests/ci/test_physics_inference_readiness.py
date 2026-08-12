# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the physics-inference readiness gate (Task 7).

The gate must emit an *honest* tier: READY_SYNTHETIC_ONLY when (as in this repo)
no licensed L2 dataset exists, READY_REALDATA_REPLAY only with a real fingerprint,
and a fail-closed BLOCKED_* verdict with an exact blocker path otherwise. It must
never promote synthetic evidence to a real-data claim.
"""

from __future__ import annotations

import pytest

# The readiness gate exercises the full Kuramoto/Ricci stack in-process, so its
# import chain pulls the heavy scientific dependencies (jax / numba / pyarrow /
# pydantic via core.*). The minimal-dependency repo-integrity gate runs tests/ci
# under a sci-core-only environment; skip there rather than fail on a missing
# optional dependency. The full coverage runs in the python-fast-shard suite.
_check = pytest.importorskip(
    "scripts.ci.check_physics_inference_readiness",
    reason="physics-inference readiness gate needs the full Kuramoto/Ricci stack",
)

READINESS_PATH = _check.READINESS_PATH
compute_readiness = _check.compute_readiness
main = _check.main

_REAL_FP = "a" * 64


def test_committed_artifact_is_ready_synthetic_only() -> None:
    assert READINESS_PATH.exists()
    assert main([]) == 0  # verify mode passes on the committed artifact


def test_synthetic_tier_is_ready_and_honest() -> None:
    result = compute_readiness(declared_tier="SYNTHETIC_ONLY", real_dataset_fingerprint=None)
    assert result["verdict"] == "READY_SYNTHETIC_ONLY", result
    assert result["blocker_path"] == "", result


def test_all_fail_closed_guards_are_live() -> None:
    result = compute_readiness(declared_tier="SYNTHETIC_ONLY", real_dataset_fingerprint=None)
    checks = result["checks"]
    assert checks["witness_index"]["ok"] is True, result
    assert checks["causality"]["ok"] is True, result
    assert checks["capsule_integrity"]["ok"] is True, result
    assert checks["synthetic_promotion"]["ok"] is True, result


def test_realdata_tier_without_real_data_is_blocked_promotion() -> None:
    result = compute_readiness(declared_tier="REALDATA_REPLAY", real_dataset_fingerprint=None)
    assert result["verdict"] == "BLOCKED_SYNTHETIC_PROMOTION", result
    assert "false promotion" in result["blocker_path"], result


def test_realdata_tier_with_synthetic_fingerprint_is_blocked() -> None:
    result = compute_readiness(
        declared_tier="REALDATA_REPLAY", real_dataset_fingerprint="synthetic:00000001"
    )
    assert result["verdict"] == "BLOCKED_SYNTHETIC_PROMOTION", result


def test_realdata_tier_with_real_fingerprint_is_ready() -> None:
    result = compute_readiness(
        declared_tier="REALDATA_REPLAY", real_dataset_fingerprint=_REAL_FP
    )
    assert result["verdict"] == "READY_REALDATA_REPLAY", result
    assert result["blocker_path"] == "", result


def test_unknown_declared_tier_is_rejected() -> None:
    with pytest.raises(ValueError, match="declared_tier"):
        compute_readiness(declared_tier="WISHFUL", real_dataset_fingerprint=None)
