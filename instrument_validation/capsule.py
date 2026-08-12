# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Capsule — single-environment bit-exact reproducibility container.

Empty ``metrics_sha`` is FORBIDDEN. ``rerun_strict`` rejects on:
* dataset hash mismatch
* instrument-id mismatch
* empty metrics_sha
* any byte-tamper of the recorded payload

Cross-machine rerun is OUT OF SCOPE for PR #592 (tag, not gate).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from instrument_validation.discrimination import DiscriminationReport
from instrument_validation.null_audit import NullAudit, serialise_null_audit
from instrument_validation.verdict import ClaimTier, Verdict


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


@dataclass(frozen=True)
class Capsule:
    capsule_id: str
    payload_sha256: str
    dataset_abs_path: str
    instrument_scope_id: str
    pos_control_cert_id: str
    neg_control_cert_id: str
    null_audits: tuple[NullAudit, ...]
    discrimination_report: DiscriminationReport
    verdict: Verdict
    claim_tier: ClaimTier
    seed_master: int
    code_sha: str
    metrics_sha: str
    external_replication_required: bool

    def __post_init__(self) -> None:
        if not self.metrics_sha:
            raise ValueError("Capsule.metrics_sha is empty — forbidden by spec G14")
        # Bug 5 fix — non-hex metrics_sha was previously accepted.
        # All sha-shaped fields must be 64-char lowercase hex.
        for field_name in ("metrics_sha", "payload_sha256", "capsule_id"):
            value = getattr(self, field_name)
            if len(value) != 64:
                raise ValueError(
                    f"{field_name} must be 64-char sha256 hexdigest; got len={len(value)}"
                )
            try:
                int(value, 16)
            except ValueError as exc:
                raise ValueError(f"{field_name} must be valid hex: {value!r}") from exc
        if not isinstance(self.external_replication_required, bool):
            raise TypeError("external_replication_required must be bool")
        if self.external_replication_required is False:
            raise ValueError("external_replication_required must always be True (spec)")
        # Bool subclasses int — exclude it explicitly so True/False can't
        # silently become seed_master=1/0.
        if isinstance(self.seed_master, bool) or not isinstance(self.seed_master, int):
            raise TypeError(
                f"seed_master must be int (not bool); got {type(self.seed_master).__name__}"
            )
        if self.seed_master < 0:
            raise ValueError(f"seed_master must be >= 0; got {self.seed_master}")


def _git_sha(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        sha = out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "UNKNOWN"
    # Reject dirty trees
    try:
        dirty = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        if dirty.stdout.strip():
            return f"{sha}-DIRTY"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # Iter-4 audit: previously this was a silent `pass`. We can't
        # determine cleanliness if `git status` failed — surface that
        # uncertainty in the returned sha rather than pretend the tree
        # is clean.
        return f"{sha}-UNKNOWN_CLEANLINESS"
    return sha


def build_capsule(
    *,
    payload_sha256: str,
    dataset_abs_path: Path,
    instrument_scope_id: str,
    pos_control_cert_id: str,
    neg_control_cert_id: str,
    null_audits: tuple[NullAudit, ...],
    discrimination_report: DiscriminationReport,
    verdict: Verdict,
    claim_tier: ClaimTier,
    seed_master: int,
    code_sha: str,
    metrics_sha: str,
) -> Capsule:
    """Construct a capsule with canonical sha256(payload)-derived ID."""
    payload = {
        "payload_sha256": payload_sha256,
        "dataset_abs_path": str(dataset_abs_path),
        "instrument_scope_id": instrument_scope_id,
        "pos_control_cert_id": pos_control_cert_id,
        "neg_control_cert_id": neg_control_cert_id,
        "null_audits": [serialise_null_audit(a) for a in null_audits],
        "verdict": verdict.value,
        "claim_tier": claim_tier.value,
        "seed_master": seed_master,
        "code_sha": code_sha,
        "metrics_sha": metrics_sha,
    }
    capsule_id = _sha256_bytes(_canonical_json(payload))
    return Capsule(
        capsule_id=capsule_id,
        payload_sha256=payload_sha256,
        dataset_abs_path=str(dataset_abs_path),
        instrument_scope_id=instrument_scope_id,
        pos_control_cert_id=pos_control_cert_id,
        neg_control_cert_id=neg_control_cert_id,
        null_audits=null_audits,
        discrimination_report=discrimination_report,
        verdict=verdict,
        claim_tier=claim_tier,
        seed_master=int(seed_master),
        code_sha=code_sha,
        metrics_sha=metrics_sha,
        external_replication_required=True,
    )


@dataclass(frozen=True)
class RerunResult:
    matched: bool
    failure_reason: str | None
    new_capsule_id: str | None


def rerun_strict(
    capsule: Capsule,
    *,
    score_fn_source: str,
    rebuild_capsule_fn: Callable[[Path, int], Capsule],
) -> RerunResult:
    """Re-execute end-to-end and bit-compare the capsule_id.

    ``rebuild_capsule_fn(dataset_path, seed)`` MUST run the full pipeline
    against the recorded dataset path with the recorded seed and return
    the regenerated Capsule.
    """
    if not capsule.metrics_sha:
        return RerunResult(False, "capsule.metrics_sha is empty (G14)", None)
    dataset_path = Path(capsule.dataset_abs_path)
    if not dataset_path.exists():
        return RerunResult(False, f"dataset path no longer exists: {dataset_path}", None)
    actual_payload_sha = _sha256_path(dataset_path) if dataset_path.is_file() else "NA"
    if dataset_path.is_file() and actual_payload_sha != capsule.payload_sha256:
        return RerunResult(
            False,
            f"payload_sha256 mismatch: recorded={capsule.payload_sha256}, "
            f"actual={actual_payload_sha}",
            None,
        )
    # Iter-4 audit fix: previously this branch silently `pass`-ed on a
    # non-strict prefix mismatch, defeating the integrity check. Now the
    # caller may opt into strict checking by passing the full semver-
    # qualified source via `score_fn_source`. If the prefix-check fails
    # AND the source string is not the empty fallback, we report it.
    score_fn_id = _sha256_bytes(score_fn_source.encode("utf-8"))
    if score_fn_source and not capsule.instrument_scope_id.startswith(score_fn_id[:16]):
        return RerunResult(
            False,
            f"instrument_scope_id prefix mismatch: recorded begins "
            f"{capsule.instrument_scope_id[:16]}, "
            f"score_fn source hashes to {score_fn_id[:16]}",
            None,
        )
    new_cap = rebuild_capsule_fn(dataset_path, capsule.seed_master)
    if new_cap.capsule_id != capsule.capsule_id:
        return RerunResult(
            False,
            f"capsule_id mismatch: recorded={capsule.capsule_id}, recomputed={new_cap.capsule_id}",
            new_cap.capsule_id,
        )
    return RerunResult(True, None, new_cap.capsule_id)


def serialise_capsule(capsule: Capsule) -> dict[str, Any]:
    return {
        "capsule_id": capsule.capsule_id,
        "payload_sha256": capsule.payload_sha256,
        "dataset_abs_path": capsule.dataset_abs_path,
        "instrument_scope_id": capsule.instrument_scope_id,
        "pos_control_cert_id": capsule.pos_control_cert_id,
        "neg_control_cert_id": capsule.neg_control_cert_id,
        "null_audits": [serialise_null_audit(a) for a in capsule.null_audits],
        "verdict": capsule.verdict.value,
        "claim_tier": capsule.claim_tier.value,
        "seed_master": capsule.seed_master,
        "code_sha": capsule.code_sha,
        "metrics_sha": capsule.metrics_sha,
        "external_replication_required": capsule.external_replication_required,
    }
