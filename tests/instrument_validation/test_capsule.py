# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G13, G14, G18 — capsule integrity + rerun_strict."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from instrument_validation.capsule import (
    Capsule,
    build_capsule,
    rerun_strict,
    serialise_capsule,
)
from instrument_validation.discrimination import (
    DiscriminationReport,
    DiscriminationVerdict,
)
from instrument_validation.null_audit import build_null_audit
from instrument_validation.verdict import ClaimTier, Verdict


def _empty_report() -> DiscriminationReport:
    return DiscriminationReport(
        metrics=tuple(),
        n_metrics_favor_ba=0,
        n_metrics_favor_er=0,
        n_metrics_not_distinguished=0,
        n_metrics_insufficient=0,
        bonferroni_k=6,
        aggregate_verdict=DiscriminationVerdict.NOT_DISTINGUISHED,
    )


def _make_capsule(tmp_path: Path, *, metrics_sha: str = "deadbeef" * 8) -> tuple[Capsule, Path]:
    rng = np.random.default_rng(0)
    audit = build_null_audit(
        null_family="er",
        null_draws=rng.normal(size=300),
        candidate=0.5,
    )
    payload_file = tmp_path / "payload.bin"
    payload_file.write_bytes(b"payload-bytes")
    payload_sha = hashlib.sha256(b"payload-bytes").hexdigest()
    cap = build_capsule(
        payload_sha256=payload_sha,
        dataset_abs_path=payload_file,
        instrument_scope_id="abc" * 22,
        pos_control_cert_id="pos" * 22,
        neg_control_cert_id="neg" * 22,
        null_audits=(audit,),
        discrimination_report=_empty_report(),
        verdict=Verdict.NOT_DISTINGUISHED,
        claim_tier=ClaimTier.NOT_DISTINGUISHED,
        seed_master=42,
        code_sha="0" * 40,
        metrics_sha=metrics_sha,
    )
    return cap, payload_file


def test_empty_metrics_sha_forbidden(tmp_path: Path) -> None:
    """G14."""
    with pytest.raises(ValueError, match="metrics_sha is empty"):
        _make_capsule(tmp_path, metrics_sha="")


def test_external_replication_required_must_be_true(tmp_path: Path) -> None:
    cap, _ = _make_capsule(tmp_path)
    with pytest.raises(ValueError, match="external_replication_required"):
        Capsule(
            capsule_id=cap.capsule_id,
            payload_sha256=cap.payload_sha256,
            dataset_abs_path=cap.dataset_abs_path,
            instrument_scope_id=cap.instrument_scope_id,
            pos_control_cert_id=cap.pos_control_cert_id,
            neg_control_cert_id=cap.neg_control_cert_id,
            null_audits=cap.null_audits,
            discrimination_report=cap.discrimination_report,
            verdict=cap.verdict,
            claim_tier=cap.claim_tier,
            seed_master=cap.seed_master,
            code_sha=cap.code_sha,
            metrics_sha=cap.metrics_sha,
            external_replication_required=False,
        )


def test_rerun_strict_detects_payload_tamper(tmp_path: Path) -> None:
    """G13."""
    cap, payload_file = _make_capsule(tmp_path)
    payload_file.write_bytes(b"TAMPERED")
    res = rerun_strict(
        cap,
        score_fn_source="",
        rebuild_capsule_fn=lambda _p, _s: cap,
    )
    assert not res.matched
    assert res.failure_reason is not None
    assert "payload_sha256 mismatch" in res.failure_reason


def test_rerun_strict_passes_on_matching_rebuild(tmp_path: Path) -> None:
    """G18."""
    cap, _ = _make_capsule(tmp_path)
    res = rerun_strict(
        cap,
        score_fn_source="",
        rebuild_capsule_fn=lambda _p, _s: cap,
    )
    assert res.matched
    assert res.new_capsule_id == cap.capsule_id


def test_serialise_capsule_round_trip_keys(tmp_path: Path) -> None:
    cap, _ = _make_capsule(tmp_path)
    payload = serialise_capsule(cap)
    for key in (
        "capsule_id",
        "payload_sha256",
        "dataset_abs_path",
        "instrument_scope_id",
        "pos_control_cert_id",
        "neg_control_cert_id",
        "null_audits",
        "verdict",
        "claim_tier",
        "seed_master",
        "code_sha",
        "metrics_sha",
        "external_replication_required",
    ):
        assert key in payload


def test_capsule_id_is_64_hex(tmp_path: Path) -> None:
    cap, _ = _make_capsule(tmp_path)
    assert len(cap.capsule_id) == 64
    int(cap.capsule_id, 16)  # valid hex


def test_capsule_rerun_strict_rejects_missing_dataset(tmp_path: Path) -> None:
    cap, payload = _make_capsule(tmp_path)
    payload.unlink()
    res = rerun_strict(
        cap,
        score_fn_source="",
        rebuild_capsule_fn=lambda _p, _s: cap,
    )
    assert not res.matched
    assert res.failure_reason is not None
    assert "no longer exists" in res.failure_reason


def test_capsule_rerun_strict_rejects_capsule_id_mismatch(tmp_path: Path) -> None:
    cap, _ = _make_capsule(tmp_path)
    other_cap, _ = _make_capsule(tmp_path, metrics_sha="cafef00d" * 8)
    res = rerun_strict(
        cap,
        score_fn_source="",
        rebuild_capsule_fn=lambda _p, _s: other_cap,
    )
    assert not res.matched
    assert res.failure_reason is not None
    assert "capsule_id mismatch" in res.failure_reason


def test_capsule_rejects_non_hex_metrics_sha(tmp_path: Path) -> None:
    """Bug 5 fix — non-hex metrics_sha was previously accepted silently."""
    with pytest.raises(ValueError, match="must be valid hex|must be 64-char"):
        _make_capsule(
            tmp_path,
            metrics_sha="not-a-hex-value-but-64-chars-padded-aaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )


def test_capsule_rejects_short_metrics_sha(tmp_path: Path) -> None:
    """Bug 5 fix — sha length must be exactly 64."""
    with pytest.raises(ValueError, match="64-char"):
        _make_capsule(tmp_path, metrics_sha="abc123")


def test_rerun_strict_rejects_instrument_scope_id_prefix_mismatch(
    tmp_path: Path,
) -> None:
    """Iter-4 audit fix: previously this branch silently `pass`-ed.

    When score_fn_source is non-empty, its sha256 prefix must match the
    capsule.instrument_scope_id prefix; otherwise rerun_strict reports
    integrity failure instead of letting it slide.
    """
    cap, _ = _make_capsule(tmp_path)
    res = rerun_strict(
        cap,
        score_fn_source="totally-different-score-source",
        rebuild_capsule_fn=lambda _p, _s: cap,
    )
    assert not res.matched
    assert res.failure_reason is not None
    assert "instrument_scope_id prefix mismatch" in res.failure_reason


def test_capsule_rejects_bool_seed(tmp_path: Path) -> None:
    """Iter-4 audit: True/False subclasses int → previously coerced
    silently to seed_master=1/0, breaking determinism semantics."""
    cap, _ = _make_capsule(tmp_path)
    with pytest.raises(TypeError, match="seed_master must be int"):
        Capsule(
            capsule_id=cap.capsule_id,
            payload_sha256=cap.payload_sha256,
            dataset_abs_path=cap.dataset_abs_path,
            instrument_scope_id=cap.instrument_scope_id,
            pos_control_cert_id=cap.pos_control_cert_id,
            neg_control_cert_id=cap.neg_control_cert_id,
            null_audits=cap.null_audits,
            discrimination_report=cap.discrimination_report,
            verdict=cap.verdict,
            claim_tier=cap.claim_tier,
            seed_master=True,
            code_sha=cap.code_sha,
            metrics_sha=cap.metrics_sha,
            external_replication_required=True,
        )


def test_capsule_rejects_negative_seed(tmp_path: Path) -> None:
    """Bug 5 fix — negative seeds break determinism semantics."""
    cap, _ = _make_capsule(tmp_path)
    with pytest.raises(ValueError, match="seed_master"):
        Capsule(
            capsule_id=cap.capsule_id,
            payload_sha256=cap.payload_sha256,
            dataset_abs_path=cap.dataset_abs_path,
            instrument_scope_id=cap.instrument_scope_id,
            pos_control_cert_id=cap.pos_control_cert_id,
            neg_control_cert_id=cap.neg_control_cert_id,
            null_audits=cap.null_audits,
            discrimination_report=cap.discrimination_report,
            verdict=cap.verdict,
            claim_tier=cap.claim_tier,
            seed_master=-1,
            code_sha=cap.code_sha,
            metrics_sha=cap.metrics_sha,
            external_replication_required=True,
        )
