# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""ReconstructionCapsule — bit-exact reproducibility for X-10R.

Mandatory ground_truth_recovery_cert_id (no claim emission without
recovery proven). Empty metrics_sha forbidden. external_replication
flag mandatory True per Protocol X-10R contract.

STATUS SURFACE — TWO PATHS  (FIX B2, INV-RECONSTRUCTION-2)
==========================================================
Synthetic-recovery path (positive controls): emits one of
    GROUND_TRUTH_RECOVERED, GROUND_TRUTH_NOT_RECOVERED,
    INVALID_RECONSTRUCTION, OUT_OF_DENSITY_BOUND.
Real-data path (no ground truth available): emits one of
    WITHIN_VALIDATED_DOMAIN, OUT_OF_VALIDATED_DOMAIN,
    INSUFFICIENT_CERTIFICATE.

By contract (enforced by `assert_real_data_status_legal` and the
test ``test_real_data_path_emits_within_or_out_never_recovered``),
emitting GROUND_TRUTH_RECOVERED on the real-data path is FORBIDDEN.
This is the exact category error INV-RECONSTRUCTION-2 prevents:
"recovery" is defined only on synthetic substrates with known truth.

TODO_PR_RECONCILE_592 (2026-05-09): once PR #592 lands, reconcile
the ClaimTier emission with the PrecursorDirection field added in
FIX B5. ClaimTier is frozen upstream; we expose direction
separately through the Gate6Result and through human-facing capsule
text — no patch-down of the frozen enum.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import numpy as np


class ReconstructionStatus(Enum):
    # Synthetic-recovery path (positive controls):
    GROUND_TRUTH_RECOVERED = "ground_truth_recovered"
    GROUND_TRUTH_NOT_RECOVERED = "ground_truth_not_recovered"
    INVALID_RECONSTRUCTION = "invalid_reconstruction"
    OUT_OF_DENSITY_BOUND = "out_of_density_bound"
    # Real-data path (no ground truth; FIX B2):
    WITHIN_VALIDATED_DOMAIN = "within_validated_domain"
    OUT_OF_VALIDATED_DOMAIN = "out_of_validated_domain"
    INSUFFICIENT_CERTIFICATE = "insufficient_certificate"


_REAL_DATA_LEGAL_STATUSES: frozenset[ReconstructionStatus] = frozenset(
    {
        ReconstructionStatus.WITHIN_VALIDATED_DOMAIN,
        ReconstructionStatus.OUT_OF_VALIDATED_DOMAIN,
        ReconstructionStatus.INSUFFICIENT_CERTIFICATE,
    }
)


_SYNTHETIC_RECOVERY_LEGAL_STATUSES: frozenset[ReconstructionStatus] = frozenset(
    {
        ReconstructionStatus.GROUND_TRUTH_RECOVERED,
        ReconstructionStatus.GROUND_TRUTH_NOT_RECOVERED,
        ReconstructionStatus.INVALID_RECONSTRUCTION,
        ReconstructionStatus.OUT_OF_DENSITY_BOUND,
    }
)


def assert_real_data_status_legal(status: ReconstructionStatus) -> None:
    """Contract: real-data path must emit a domain-of-validity status.

    GROUND_TRUTH_RECOVERED on real data is the exact category error
    INV-RECONSTRUCTION-2 forbids ("recovery" is undefined where there
    is no ground truth). Fail-closed at the boundary, with a message
    that names the violated invariant so reviewers can trace it.
    """
    if status not in _REAL_DATA_LEGAL_STATUSES:
        raise ValueError(
            "INV-RECONSTRUCTION-2 VIOLATED: real-data reconstruction status must "
            f"be one of {sorted(s.value for s in _REAL_DATA_LEGAL_STATUSES)}; "
            f"got {status.value!r}. On real inputs there is no ground truth, so "
            "GROUND_TRUTH_RECOVERED / GROUND_TRUTH_NOT_RECOVERED are forbidden."
        )


def assert_synthetic_status_legal(status: ReconstructionStatus) -> None:
    """Contract: synthetic-recovery path must emit a recovery status."""
    if status not in _SYNTHETIC_RECOVERY_LEGAL_STATUSES:
        raise ValueError(
            "INV-RECONSTRUCTION-1 VIOLATED: synthetic reconstruction status must "
            f"be one of {sorted(s.value for s in _SYNTHETIC_RECOVERY_LEGAL_STATUSES)}; "
            f"got {status.value!r}. Domain-of-validity statuses are reserved "
            "for the real-data path — they cannot certify ground-truth recovery."
        )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _is_valid_hex(value: str, length: int = 64) -> bool:
    if len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class ReconstructionCapsule:
    capsule_id: str
    payload_sha256: str
    scope_id: str
    inferred_density: float
    spectral_radius: float
    L1_error_row: float
    L1_error_col: float
    n_nodes: int
    z_calibrated: float
    prng_seed: int
    ground_truth_recovery_cert_id: str  # MANDATORY non-empty
    kuramoto_recovery_cert_id: str | None
    reconstruction_status: ReconstructionStatus
    code_sha: str
    metrics_sha: str
    external_replication_required: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.metrics_sha:
            raise ValueError("ReconstructionCapsule.metrics_sha is empty — forbidden")
        if not self.ground_truth_recovery_cert_id:
            raise ValueError(
                "ground_truth_recovery_cert_id is mandatory and non-empty "
                "(no verdict without proven recovery — INV-RECONSTRUCTION-1)"
            )
        for fname in ("metrics_sha", "payload_sha256", "capsule_id"):
            value = getattr(self, fname)
            if not _is_valid_hex(value):
                raise ValueError(f"{fname} must be 64-char lowercase hex; got {value!r}")
        if not isinstance(self.external_replication_required, bool):
            raise TypeError("external_replication_required must be bool")
        if self.external_replication_required is False:
            raise ValueError("external_replication_required must always be True (spec)")
        if isinstance(self.prng_seed, bool) or not isinstance(self.prng_seed, int):
            raise TypeError(
                f"prng_seed must be int (not bool); got {type(self.prng_seed).__name__}"
            )
        if self.prng_seed < 0:
            raise ValueError(f"prng_seed must be >= 0; got {self.prng_seed}")
        if self.n_nodes < 2:
            raise ValueError(f"n_nodes must be >= 2; got {self.n_nodes}")


def build_reconstruction_capsule(
    *,
    payload_sha256: str,
    scope_id: str,
    inferred_density: float,
    spectral_radius: float,
    L1_error_row: float,
    L1_error_col: float,
    n_nodes: int,
    z_calibrated: float,
    prng_seed: int,
    ground_truth_recovery_cert_id: str,
    kuramoto_recovery_cert_id: str | None,
    reconstruction_status: ReconstructionStatus,
    code_sha: str,
    metrics_sha: str,
    extra: dict[str, Any] | None = None,
) -> ReconstructionCapsule:
    if isinstance(prng_seed, bool) or not isinstance(prng_seed, int):
        raise TypeError(f"prng_seed must be int (not bool); got {type(prng_seed).__name__}")
    payload = {
        "payload_sha256": payload_sha256,
        "scope_id": scope_id,
        "inferred_density": round(inferred_density, 12),
        "spectral_radius": round(spectral_radius, 12),
        "L1_error_row": round(L1_error_row, 12),
        "L1_error_col": round(L1_error_col, 12),
        "n_nodes": int(n_nodes),
        "z_calibrated": round(z_calibrated, 12),
        "prng_seed": int(prng_seed),
        "ground_truth_recovery_cert_id": ground_truth_recovery_cert_id,
        "kuramoto_recovery_cert_id": kuramoto_recovery_cert_id,
        "reconstruction_status": reconstruction_status.value,
        "code_sha": code_sha,
        "metrics_sha": metrics_sha,
    }
    capsule_id = _sha256_bytes(_canonical_json(payload))
    return ReconstructionCapsule(
        capsule_id=capsule_id,
        payload_sha256=payload_sha256,
        scope_id=scope_id,
        inferred_density=float(inferred_density),
        spectral_radius=float(spectral_radius),
        L1_error_row=float(L1_error_row),
        L1_error_col=float(L1_error_col),
        n_nodes=int(n_nodes),
        z_calibrated=float(z_calibrated),
        prng_seed=int(prng_seed),
        ground_truth_recovery_cert_id=ground_truth_recovery_cert_id,
        kuramoto_recovery_cert_id=kuramoto_recovery_cert_id,
        reconstruction_status=reconstruction_status,
        code_sha=code_sha,
        metrics_sha=metrics_sha,
        external_replication_required=True,
        extra=dict(extra or {}),
    )


@dataclass(frozen=True)
class ReconstructionRerunResult:
    matched: bool
    failure_reason: str | None
    new_capsule_id: str | None


def rerun_reconstruction_strict(
    capsule: ReconstructionCapsule,
    *,
    rebuild_capsule_fn: Callable[[int], ReconstructionCapsule],
) -> ReconstructionRerunResult:
    """Re-execute end-to-end with the recorded prng_seed; bit-compare."""
    if not capsule.metrics_sha:
        return ReconstructionRerunResult(False, "metrics_sha is empty (forbidden)", None)
    if not capsule.ground_truth_recovery_cert_id:
        return ReconstructionRerunResult(
            False, "ground_truth_recovery_cert_id is empty (forbidden)", None
        )
    new_cap = rebuild_capsule_fn(capsule.prng_seed)
    if new_cap.capsule_id != capsule.capsule_id:
        return ReconstructionRerunResult(
            False,
            f"capsule_id mismatch: recorded={capsule.capsule_id}, recomputed={new_cap.capsule_id}",
            new_cap.capsule_id,
        )
    return ReconstructionRerunResult(True, None, new_cap.capsule_id)


def serialise_reconstruction_capsule(capsule: ReconstructionCapsule) -> dict[str, Any]:
    return {
        "capsule_id": capsule.capsule_id,
        "payload_sha256": capsule.payload_sha256,
        "scope_id": capsule.scope_id,
        "inferred_density": capsule.inferred_density,
        "spectral_radius": capsule.spectral_radius,
        "L1_error_row": capsule.L1_error_row,
        "L1_error_col": capsule.L1_error_col,
        "n_nodes": capsule.n_nodes,
        "z_calibrated": capsule.z_calibrated,
        "prng_seed": capsule.prng_seed,
        "ground_truth_recovery_cert_id": capsule.ground_truth_recovery_cert_id,
        "kuramoto_recovery_cert_id": capsule.kuramoto_recovery_cert_id,
        "reconstruction_status": capsule.reconstruction_status.value,
        "code_sha": capsule.code_sha,
        "metrics_sha": capsule.metrics_sha,
        "external_replication_required": capsule.external_replication_required,
        "extra": dict(capsule.extra),
    }


def hash_marginals(s_out: np.ndarray, s_in: np.ndarray) -> str:
    """sha256 of canonicalised (s_out, s_in) — for payload_sha256."""
    s_out_arr = np.round(np.asarray(s_out, dtype=np.float64), 9)
    s_in_arr = np.round(np.asarray(s_in, dtype=np.float64), 9)
    return _sha256_bytes(s_out_arr.tobytes() + b"|" + s_in_arr.tobytes())
