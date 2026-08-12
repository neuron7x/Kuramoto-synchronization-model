# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for the metric_distortion_bound law."""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.metric_consistency import (
    assert_distortion_bound,
    condition_number,
    distortion,
    pairwise_distances,
    perturb_embedding,
)


def _grid_points(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, size=(12, 3))


def test_isometric_embedding_passes() -> None:
    """Positive witness: a rigid transform (rotation + translation) is an isometry."""
    pts = _grid_points(1)
    d_orig = pairwise_distances(pts)
    # Rotation about z + translation preserves Euclidean distances exactly.
    theta = 0.7
    rot = np.array(
        [[np.cos(theta), -np.sin(theta), 0.0], [np.sin(theta), np.cos(theta), 0.0], [0.0, 0.0, 1.0]]
    )
    embedded = pts @ rot.T + np.array([5.0, -2.0, 1.0])
    d_emb = pairwise_distances(embedded)
    measured = assert_distortion_bound(d_orig, d_emb, max_distortion=1e-9)
    assert abs(measured - 1.0) <= 1e-9


def test_distorted_embedding_is_rejected() -> None:
    """Negative control: an anisotropically stretched embedding breaks the bound."""
    pts = _grid_points(2)
    d_orig = pairwise_distances(pts)
    stretched = pts * np.array([3.0, 1.0, 1.0])  # 3x along one axis → large distortion
    d_emb = pairwise_distances(stretched)
    with pytest.raises(ValueError, match="METRIC-DISTORTION VIOLATED"):
        assert_distortion_bound(d_orig, d_emb, max_distortion=0.05)


def test_perturbation_beyond_epsilon_fails() -> None:
    """A large seeded perturbation pushes distortion past a tight bound."""
    pts = _grid_points(3)
    d_orig = pairwise_distances(pts)
    noisy = perturb_embedding(pts, epsilon=0.5, seed=3)
    d_emb = pairwise_distances(noisy)
    with pytest.raises(ValueError, match="METRIC-DISTORTION VIOLATED"):
        assert_distortion_bound(d_orig, d_emb, max_distortion=0.01)


def test_singular_metric_is_rejected() -> None:
    """A NaN/Inf or coincident-point distance matrix fails closed."""
    pts = _grid_points(4)
    d_orig = pairwise_distances(pts)
    bad = d_orig.copy()
    bad[0, 1] = bad[1, 0] = 0.0  # coincident off-diagonal → degenerate
    with pytest.raises(ValueError, match="zero/degenerate"):
        distortion(d_orig, bad)


def test_disconnected_metric_is_rejected() -> None:
    """A non-finite (disconnected/infinite) distance fails closed."""
    pts = _grid_points(5)
    d = pairwise_distances(pts)
    d[2, 3] = d[3, 2] = np.inf
    with pytest.raises(ValueError, match="NaN/Inf"):
        distortion(d, d)


def test_thresholds_are_explicit_not_magic() -> None:
    """The bound is a required explicit argument; a negative bound is rejected."""
    pts = _grid_points(6)
    d = pairwise_distances(pts)
    with pytest.raises(ValueError, match="max_distortion must be finite and >= 0"):
        assert_distortion_bound(d, d, max_distortion=-1.0)


def test_condition_number_of_singular_matrix_is_huge() -> None:
    """A singular matrix has an enormous condition number (ill-posed inversion).

    NumPy's SVD-based cond of an exactly-singular matrix returns a finite but
    astronomically large value (~1/eps), not literal inf — either way it is far
    past any usable ceiling.
    """
    singular = np.array([[1.0, 2.0], [2.0, 4.0]])
    assert condition_number(singular) > 1e15
    assert condition_number(np.eye(3)) == 1.0


def test_non_square_metric_is_rejected() -> None:
    """`ndim != 2 or shape[0] != shape[1]` -- a 2D non-square matrix fails.

    Rule-Zero note: this guards the METRIC CONTRACT (a distance matrix is square);
    it redefines no physical quantity. Under Or->And a valid ndim cancels the
    non-square fault and a malformed metric would be measured.
    """
    square = np.array([[0.0, 1.0], [1.0, 0.0]])
    non_square = np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 3.0]])
    with pytest.raises(ValueError, match="square"):
        distortion(non_square, square)


def test_negative_epsilon_perturbation_is_rejected() -> None:
    """`not isfinite(epsilon) or epsilon < 0.0` -- a finite negative fails.

    Under Or->And a finite but negative noise scale slips past the guard.
    """
    pts = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    with pytest.raises(ValueError, match="epsilon"):
        perturb_embedding(pts, epsilon=-1.0, seed=0)
