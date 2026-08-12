# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G8 — NullAudit raises on missing quantiles or insufficient draws."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from instrument_validation.null_audit import (
    REQUIRED_QUANTILES,
    NullAudit,
    build_null_audit,
    serialise_null_audit,
)


def _stub_sha() -> str:
    return hashlib.sha256(b"x").hexdigest()


def test_null_audit_rejects_missing_quantile() -> None:
    qs = {q: 0.0 for q in REQUIRED_QUANTILES if q != "p50"}
    with pytest.raises(ValueError, match="missing required quantiles"):
        NullAudit(
            null_family="x",
            null_mean=0.0,
            null_std=1.0,
            quantiles=qs,
            candidate=0.0,
            candidate_percentile=50.0,
            empirical_p_one_sided=0.5,
            z_score=0.0,
            n_null_draws=200,
            null_draws_sha256=_stub_sha(),
        )


def test_null_audit_rejects_too_few_draws() -> None:
    qs = {q: 0.0 for q in REQUIRED_QUANTILES}
    with pytest.raises(ValueError, match="< required"):
        NullAudit(
            null_family="x",
            null_mean=0.0,
            null_std=1.0,
            quantiles=qs,
            candidate=0.0,
            candidate_percentile=50.0,
            empirical_p_one_sided=0.5,
            z_score=0.0,
            n_null_draws=100,
            null_draws_sha256=_stub_sha(),
        )


def test_null_audit_rejects_bad_sha_length() -> None:
    qs = {q: 0.0 for q in REQUIRED_QUANTILES}
    with pytest.raises(ValueError, match="sha256"):
        NullAudit(
            null_family="x",
            null_mean=0.0,
            null_std=1.0,
            quantiles=qs,
            candidate=0.0,
            candidate_percentile=50.0,
            empirical_p_one_sided=0.5,
            z_score=0.0,
            n_null_draws=200,
            null_draws_sha256="short",
        )


def test_build_null_audit_full_pipeline() -> None:
    rng = np.random.default_rng(7)
    draws = rng.normal(0.0, 1.0, 500)
    audit = build_null_audit(
        null_family="erdos_renyi",
        null_draws=draws,
        candidate=2.5,
        one_sided="candidate_above_null",
    )
    assert audit.n_null_draws == 500
    assert set(audit.quantiles.keys()) == set(REQUIRED_QUANTILES)
    assert audit.candidate == 2.5
    assert 0.0 <= audit.empirical_p_one_sided <= 1.0
    assert 0.0 <= audit.candidate_percentile <= 100.0
    assert len(audit.null_draws_sha256) == 64


def test_build_null_audit_rejects_low_draws() -> None:
    with pytest.raises(ValueError, match="finite null draws"):
        build_null_audit(
            null_family="x",
            null_draws=np.zeros(50),
            candidate=0.0,
        )


def test_build_null_audit_rejects_invalid_one_sided() -> None:
    """Iter-4 audit fix — invalid one_sided was detected only after
    expensive percentile computation; now fails fast."""
    with pytest.raises(ValueError, match="one_sided must be one of"):
        build_null_audit(
            null_family="x",
            null_draws=np.random.default_rng(0).normal(size=300),
            candidate=0.0,
            one_sided="typo_not_a_real_choice",
        )


def test_build_null_audit_rejects_empty_null_family() -> None:
    """Iter-4 audit fix — empty null_family was previously stored as-is."""
    with pytest.raises(ValueError, match="null_family"):
        build_null_audit(
            null_family="",
            null_draws=np.random.default_rng(0).normal(size=300),
            candidate=0.0,
        )


def test_serialise_null_audit_round_trip() -> None:
    rng = np.random.default_rng(0)
    audit = build_null_audit(
        null_family="er",
        null_draws=rng.normal(size=300),
        candidate=0.0,
    )
    payload = serialise_null_audit(audit)
    for key in (
        "null_family",
        "null_mean",
        "null_std",
        "quantiles",
        "candidate",
        "candidate_percentile",
        "empirical_p_one_sided",
        "z_score",
        "n_null_draws",
        "null_draws_sha256",
        "extra",
    ):
        assert key in payload
