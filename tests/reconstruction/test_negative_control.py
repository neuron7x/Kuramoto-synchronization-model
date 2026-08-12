# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for negative_control.py — null protocols + discriminativity."""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.negative_control import (
    NegativeControlCertificate,
    NegFalsePositiveError,
    neg_2d_grid,
    neg_path_lattice,
    neg_ring_lattice,
    run_all_negative_controls,
    run_negative_control,
)


def test_ring_lattice_shape_and_diagonal() -> None:
    w = neg_ring_lattice(n=80, k=3)
    assert w.shape == (80, 80)
    assert np.all(np.diag(w) == 0.0)
    # Each row has exactly 2k non-zero entries
    assert np.all((w > 0).sum(axis=1) == 2 * 3)


def test_ring_lattice_uniform_marginals() -> None:
    w = neg_ring_lattice(n=80, k=4, w_unit=1.0)
    s_out = w.sum(axis=1)
    np.testing.assert_allclose(s_out, s_out[0])


def test_path_lattice_endpoints_have_one_neighbour() -> None:
    w = neg_path_lattice(n=20, w_unit=1.0)
    # Endpoint 0 connects only to 1
    assert (w[0] > 0).sum() == 1
    # Endpoint n-1 connects only to n-2
    assert (w[-1] > 0).sum() == 1
    # Interior nodes connect to 2 neighbours
    assert (w[5] > 0).sum() == 2


def test_2d_grid_perfect_square_only() -> None:
    with pytest.raises(ValueError, match="perfect square"):
        neg_2d_grid(n=200)
    # 196 = 14 × 14 OK
    w = neg_2d_grid(n=196)
    assert w.shape == (196, 196)


def test_2d_grid_interior_node_has_4_neighbours() -> None:
    w = neg_2d_grid(n=100)  # 10×10
    # Interior node (5,5) → index 55 has 4 neighbours
    assert (w[55] > 0).sum() == 4
    # Corner node (0,0) → index 0 has 2 neighbours
    assert (w[0] > 0).sum() == 2


def test_ring_lattice_rejects_n_too_small() -> None:
    with pytest.raises(ValueError):
        neg_ring_lattice(n=5, k=4)


def test_path_lattice_rejects_negative_w_unit() -> None:
    with pytest.raises(ValueError):
        neg_path_lattice(n=20, w_unit=-1.0)


def test_2d_grid_rejects_small_side() -> None:
    with pytest.raises(ValueError):
        neg_2d_grid(n=9)  # sqrt=3, < 4


def test_run_negative_control_certifies_discriminativity_on_lattice() -> None:
    w = neg_ring_lattice(n=200, k=4)
    cert = run_negative_control("RING", w, seed=42)
    assert isinstance(cert, NegativeControlCertificate)
    assert cert.instrument_is_discriminative is True
    # All 4 densities should fail Gate 5 on a lattice null
    n_failed = sum(1 for p in cert.per_density_passed.values() if not p)
    assert n_failed >= 1


def test_run_negative_control_raises_on_false_positive() -> None:
    """If the 'null' is actually recoverable (e.g., random log-normal weights
    on the same support), Gate 5 passes everywhere — instrument is NOT
    discriminative on this null and NegFalsePositiveError must fire."""
    rng = np.random.default_rng(0)
    n = 60
    s = rng.lognormal(mean=10.0, sigma=1.5, size=n)
    s_in = s.copy()
    rng.shuffle(s_in)
    s_in *= s.sum() / s_in.sum()
    # Build a recoverable W from these marginals: outer product / total.
    w_recoverable = np.outer(s, s_in) / s.sum()
    np.fill_diagonal(w_recoverable, 0.0)
    with pytest.raises(NegFalsePositiveError):
        run_negative_control("RECOVERABLE", w_recoverable, seed=42)


def test_run_all_negative_controls_returns_three_certs() -> None:
    res = run_all_negative_controls(n=200, seed=42)
    assert set(res.keys()) == {"NEG_RING_LATTICE", "NEG_PATH_LATTICE", "NEG_2D_GRID"}
    for cert in res.values():
        assert cert.is_valid()
        assert cert.instrument_is_discriminative is True


def test_negative_control_cert_id_is_64_hex() -> None:
    w = neg_ring_lattice(n=100, k=3)
    cert = run_negative_control("RING_TEST", w, seed=0)
    assert len(cert.cert_id) == 64
    int(cert.cert_id, 16)


def test_negative_control_cert_id_seed_sensitive() -> None:
    w = neg_ring_lattice(n=100, k=3)
    cert_a = run_negative_control("RING", w, seed=0)
    cert_b = run_negative_control("RING", w, seed=1)
    assert cert_a.cert_id != cert_b.cert_id
