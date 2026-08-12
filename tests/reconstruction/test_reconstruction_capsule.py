# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for reconstruction_capsule.py — bit-exact rerun + invariants."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pytest

from research.reconstruction.reconstruction_capsule import (
    ReconstructionCapsule,
    ReconstructionStatus,
    build_reconstruction_capsule,
    hash_marginals,
    rerun_reconstruction_strict,
    serialise_reconstruction_capsule,
)


def _good_args() -> dict[str, Any]:
    return dict(
        payload_sha256=hashlib.sha256(b"x").hexdigest(),
        scope_id="x10r/test/2026-05-09",
        inferred_density=0.05,
        spectral_radius=1.5e6,
        L1_error_row=1.0e-10,
        L1_error_col=1.0e-10,
        n_nodes=200,
        z_calibrated=12.34,
        prng_seed=42,
        ground_truth_recovery_cert_id=hashlib.sha256(b"gt").hexdigest(),
        kuramoto_recovery_cert_id=hashlib.sha256(b"kr").hexdigest(),
        reconstruction_status=ReconstructionStatus.GROUND_TRUTH_RECOVERED,
        code_sha=hashlib.sha256(b"code").hexdigest(),
        metrics_sha=hashlib.sha256(b"metrics").hexdigest(),
    )


def test_build_capsule_round_trip() -> None:
    cap = build_reconstruction_capsule(**_good_args())
    assert isinstance(cap, ReconstructionCapsule)
    assert cap.external_replication_required is True
    assert cap.reconstruction_status == ReconstructionStatus.GROUND_TRUTH_RECOVERED


def test_capsule_id_is_deterministic_for_same_payload() -> None:
    cap_a = build_reconstruction_capsule(**_good_args())
    cap_b = build_reconstruction_capsule(**_good_args())
    assert cap_a.capsule_id == cap_b.capsule_id


def test_capsule_id_changes_with_seed() -> None:
    args_a = _good_args()
    args_b = dict(args_a)
    args_b["prng_seed"] = 43
    assert (
        build_reconstruction_capsule(**args_a).capsule_id
        != build_reconstruction_capsule(**args_b).capsule_id
    )


def test_empty_metrics_sha_forbidden() -> None:
    args = _good_args()
    args["metrics_sha"] = ""
    with pytest.raises(ValueError, match="metrics_sha"):
        build_reconstruction_capsule(**args)


def test_empty_ground_truth_cert_forbidden() -> None:
    args = _good_args()
    args["ground_truth_recovery_cert_id"] = ""
    with pytest.raises(ValueError, match="ground_truth_recovery_cert_id"):
        build_reconstruction_capsule(**args)


def test_invalid_metrics_sha_format_rejected() -> None:
    args = _good_args()
    args["metrics_sha"] = "not-a-valid-hex"
    with pytest.raises(ValueError, match="metrics_sha"):
        build_reconstruction_capsule(**args)


def test_external_replication_always_true() -> None:
    cap = build_reconstruction_capsule(**_good_args())
    # The flag is hardcoded True; cannot be changed by the constructor.
    assert cap.external_replication_required is True


def test_negative_seed_rejected() -> None:
    args = _good_args()
    args["prng_seed"] = -1
    with pytest.raises(ValueError):
        build_reconstruction_capsule(**args)


def test_bool_seed_rejected() -> None:
    """bool subclasses int but must be rejected explicitly."""
    args = _good_args()
    args["prng_seed"] = True
    with pytest.raises(TypeError):
        build_reconstruction_capsule(**args)


def test_n_nodes_too_small_rejected() -> None:
    args = _good_args()
    args["n_nodes"] = 1
    with pytest.raises(ValueError):
        build_reconstruction_capsule(**args)


def test_serialise_round_trip() -> None:
    cap = build_reconstruction_capsule(**_good_args())
    payload = serialise_reconstruction_capsule(cap)
    assert payload["capsule_id"] == cap.capsule_id
    assert payload["external_replication_required"] is True
    assert payload["reconstruction_status"] == ReconstructionStatus.GROUND_TRUTH_RECOVERED.value


def test_rerun_strict_matches() -> None:
    cap = build_reconstruction_capsule(**_good_args())

    def rebuild(seed: int) -> ReconstructionCapsule:
        args = _good_args()
        args["prng_seed"] = seed
        return build_reconstruction_capsule(**args)

    res = rerun_reconstruction_strict(cap, rebuild_capsule_fn=rebuild)
    assert res.matched is True
    assert res.failure_reason is None


def test_rerun_strict_detects_drift() -> None:
    cap = build_reconstruction_capsule(**_good_args())

    def drifted_rebuild(seed: int) -> ReconstructionCapsule:
        args = _good_args()
        args["prng_seed"] = seed
        args["spectral_radius"] = 2.0e6  # different
        return build_reconstruction_capsule(**args)

    res = rerun_reconstruction_strict(cap, rebuild_capsule_fn=drifted_rebuild)
    assert res.matched is False
    assert res.failure_reason is not None and "capsule_id mismatch" in res.failure_reason


def test_hash_marginals_is_deterministic() -> None:
    rng = np.random.default_rng(0)
    s_out = rng.uniform(0.0, 100.0, size=20)
    s_in = rng.uniform(0.0, 100.0, size=20)
    h_a = hash_marginals(s_out, s_in)
    h_b = hash_marginals(s_out, s_in)
    assert h_a == h_b
    assert len(h_a) == 64


def test_hash_marginals_changes_with_input() -> None:
    s_out = np.array([1.0, 2.0, 3.0])
    s_in = np.array([2.0, 1.0, 3.0])
    h_a = hash_marginals(s_out, s_in)
    h_b = hash_marginals(s_out + 1.0, s_in)
    assert h_a != h_b


# ---------------------------------------------------------------------------
# Gate 4 — bit-exact reproducibility (explicit Protocol X-10R names).
# These are named per protocol (test_gate_4_*) to make Gate 4 enforcement
# auditable from the spec rather than only via internal helpers.
# ---------------------------------------------------------------------------


def test_gate_4_bit_exact_rerun_with_fixed_prng() -> None:
    """Gate 4: identical canonical inputs (incl. fixed prng_seed) ⇒
    bit-identical capsule_id. This is the determinism contract that
    every X-10R verdict is anchored on."""
    args = _good_args()
    args["prng_seed"] = 20260509
    cap_a = build_reconstruction_capsule(**args)
    cap_b = build_reconstruction_capsule(**args)
    assert cap_a.capsule_id == cap_b.capsule_id
    assert cap_a.payload_sha256 == cap_b.payload_sha256
    assert cap_a.metrics_sha == cap_b.metrics_sha
    assert cap_a.code_sha == cap_b.code_sha
    assert cap_a.spectral_radius == cap_b.spectral_radius


def test_gate_4_payload_tamper_breaks_rerun() -> None:
    """Gate 4: tampering ANY payload field must change capsule_id —
    otherwise determinism is decoupled from inputs and replay is theatre."""
    args_a = _good_args()
    args_a["prng_seed"] = 20260509
    cap_a = build_reconstruction_capsule(**args_a)

    # Tamper a single float byte at the 12-decimal canonicalisation boundary.
    args_b = dict(args_a)
    args_b["spectral_radius"] = args_a["spectral_radius"] + 1e-9
    cap_b = build_reconstruction_capsule(**args_b)
    assert cap_a.capsule_id != cap_b.capsule_id

    # Tamper payload_sha256 (hash of the marginals).
    args_c = dict(args_a)
    args_c["payload_sha256"] = hashlib.sha256(b"tampered").hexdigest()
    cap_c = build_reconstruction_capsule(**args_c)
    assert cap_a.capsule_id != cap_c.capsule_id

    # Tamper metrics_sha.
    args_d = dict(args_a)
    args_d["metrics_sha"] = hashlib.sha256(b"different-metrics").hexdigest()
    cap_d = build_reconstruction_capsule(**args_d)
    assert cap_a.capsule_id != cap_d.capsule_id
