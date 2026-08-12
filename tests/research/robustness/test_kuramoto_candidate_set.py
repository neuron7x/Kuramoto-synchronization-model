# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Candidate-set anti-inflation guard tests."""

from __future__ import annotations

import pytest

from research.robustness.protocols.kuramoto_candidate_set import (
    CandidateSetInflationError,
    assert_anchor_covers_candidates,
    validate_candidate_parameter_names,
)


def test_legit_names_accepted() -> None:
    """NON_PHYSICS: candidate-set name-governance guard (no physical quantity)."""
    validate_candidate_parameter_names({"cost_bps": 0.1, "vol_target_annualised": 0.05})


@pytest.mark.parametrize(
    "bad",
    [
        "seed_value",
        "random_noise_scale",
        "jitter_extra",
    ],
)
def test_forbidden_prefixes_rejected(bad: str) -> None:
    """NON_PHYSICS: candidate-set anti-inflation name guard (no physics)."""
    with pytest.raises(CandidateSetInflationError):
        validate_candidate_parameter_names({bad: 0.1})


def test_multiple_offenders_listed_together() -> None:
    """NON_PHYSICS: name-governance error-message guard (no physics)."""
    with pytest.raises(CandidateSetInflationError) as exc:
        validate_candidate_parameter_names({"seed_a": 0.1, "random_b": 0.1, "cost_bps": 0.2})
    msg = str(exc.value)
    assert "seed_a" in msg
    assert "random_b" in msg
    assert "cost_bps" not in msg


def test_missing_anchor_key_rejected() -> None:
    """NON_PHYSICS: anchor-coverage governance guard (no physical quantity)."""
    with pytest.raises(CandidateSetInflationError):
        assert_anchor_covers_candidates(
            {"cost_bps": 1.0},
            {"nonexistent": 0.1},
        )
