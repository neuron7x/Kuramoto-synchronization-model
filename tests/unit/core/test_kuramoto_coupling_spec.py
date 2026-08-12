# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Stream-1 contract tests for ``core.kuramoto.coupling_spec``.

Enforces the first principle *coupling appears exactly once*:

* a global scalar ``K`` and a full physical weight matrix ``W`` encode the same
  coupling and must agree (``K·A ≡ W``);
* re-scaling an already-physical ``W`` by a non-unit ``K`` is rejected
  (anti-double-scaling);
* negative ``K`` / negative weights are admissible only under an explicitly
  signed claim boundary, and a signed coupling can never advertise the
  attractive-Kuramoto boundary;
* the effective matrix used by :class:`KuramotoConfig` enters the dynamics
  exactly once.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.coupling_spec import (
    CLAIM_ATTRACTIVE,
    CLAIM_SIGNED,
    CouplingMode,
    CouplingSpec,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def normalized_A() -> np.ndarray:
    """Row-normalized non-negative topology (rows sum to 1, zero diagonal)."""
    rng = np.random.default_rng(7)
    a = rng.uniform(0.0, 1.0, size=(5, 5))
    np.fill_diagonal(a, 0.0)
    a /= a.sum(axis=1, keepdims=True)
    return np.asarray(a, dtype=np.float64)


# ---------------------------------------------------------------------------
# Equivalence: the two conventions encode the same coupling
# ---------------------------------------------------------------------------


def test_k_a_equivalent_to_w_to_tolerance(normalized_A: np.ndarray) -> None:
    """``C = K·A`` (global) must equal ``C = W`` when ``W := K·A`` (full)."""
    K = 2.5
    global_spec = CouplingSpec.global_normalized(K, normalized_A)
    W = K * normalized_A
    full_spec = CouplingSpec.full_weight(W)

    np.testing.assert_allclose(
        global_spec.effective_matrix(),
        full_spec.effective_matrix(),
        rtol=0.0,
        atol=1e-12,
    )


# ---------------------------------------------------------------------------
# Anti-double-scaling
# ---------------------------------------------------------------------------


def test_double_scaling_rejected(normalized_A: np.ndarray) -> None:
    """A full physical ``W`` with a non-unit ``K`` would double-scale → reject."""
    W = 2.5 * normalized_A
    with pytest.raises(ValueError, match="double-scaling"):
        CouplingSpec(matrix=W, mode=CouplingMode.FULL_WEIGHT_MATRIX_W, K=2.5)


def test_pre_scaled_w_passed_as_signed_weight_rejects_nonunit_k(
    normalized_A: np.ndarray,
) -> None:
    """Signed full-weight matrices are equally protected from re-scaling."""
    W = normalized_A - normalized_A.T  # signed
    with pytest.raises(ValueError, match="double-scaling"):
        CouplingSpec(matrix=W, mode=CouplingMode.SIGNED_POS_NEG_CHANNELS, K=3.0)


def test_full_weight_with_unit_k_accepted(normalized_A: np.ndarray) -> None:
    spec = CouplingSpec.full_weight(2.5 * normalized_A)
    assert spec.K == 1.0
    assert spec.effective_matrix().shape == (5, 5)


# ---------------------------------------------------------------------------
# Sign discipline + claim boundary
# ---------------------------------------------------------------------------


def test_negative_k_rejected_in_attractive_mode(normalized_A: np.ndarray) -> None:
    with pytest.raises(ValueError, match="negative K"):
        CouplingSpec.global_normalized(-1.0, normalized_A)


def test_negative_k_allowed_only_in_repulsive_mode(normalized_A: np.ndarray) -> None:
    spec = CouplingSpec.repulsive_global(-1.5, normalized_A)
    assert spec.claim_boundary == CLAIM_SIGNED


def test_negative_weight_rejected_in_attractive_full_weight(
    normalized_A: np.ndarray,
) -> None:
    W = normalized_A.copy()
    W[0, 1] = -0.3
    with pytest.raises(ValueError, match="attractive"):
        CouplingSpec.full_weight(W)


def test_signed_negative_edges_allowed_only_in_signed_config(
    normalized_A: np.ndarray,
) -> None:
    W = normalized_A.copy()
    W[0, 1] = -0.3
    spec = CouplingSpec.signed_weight(W)
    assert spec.effective_matrix()[0, 1] == pytest.approx(-0.3)


def test_signed_mode_cannot_emit_attractive_claim_boundary(
    normalized_A: np.ndarray,
) -> None:
    for spec in (
        CouplingSpec.signed_weight(normalized_A - normalized_A.T),
        CouplingSpec.repulsive_global(-2.0, normalized_A),
    ):
        assert spec.claim_boundary == CLAIM_SIGNED
        assert spec.claim_boundary != CLAIM_ATTRACTIVE


def test_attractive_modes_emit_attractive_claim_boundary(
    normalized_A: np.ndarray,
) -> None:
    for spec in (
        CouplingSpec.global_normalized(1.5, normalized_A),
        CouplingSpec.full_weight(normalized_A),
    ):
        assert spec.claim_boundary == CLAIM_ATTRACTIVE


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


def test_nonfinite_coupling_rejected(normalized_A: np.ndarray) -> None:
    bad = normalized_A.copy()
    bad[2, 3] = np.inf
    with pytest.raises(ValueError, match="NaN or Inf"):
        CouplingSpec.full_weight(bad)


def test_shape_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="2x2|square|shape"):
        CouplingSpec.full_weight(np.ones((3, 4), dtype=np.float64))


def test_nonfinite_k_rejected(normalized_A: np.ndarray) -> None:
    with pytest.raises(ValueError, match="K must be finite"):
        CouplingSpec.global_normalized(np.nan, normalized_A)


def test_too_small_matrix_rejected() -> None:
    with pytest.raises(ValueError, match="at least 2x2"):
        CouplingSpec.full_weight(np.zeros((1, 1), dtype=np.float64))


def test_matrix_is_frozen(normalized_A: np.ndarray) -> None:
    spec = CouplingSpec.full_weight(normalized_A)
    with pytest.raises(ValueError):
        spec.matrix[0, 0] = 1.0


def test_effective_matrix_zeroes_diagonal() -> None:
    W = np.ones((4, 4), dtype=np.float64)  # nonzero diagonal on purpose
    spec = CouplingSpec.full_weight(W)
    assert np.all(np.diag(spec.effective_matrix()) == 0.0)


# ---------------------------------------------------------------------------
# Metadata / provenance
# ---------------------------------------------------------------------------


def test_coupling_metadata_emitted(normalized_A: np.ndarray) -> None:
    spec = CouplingSpec.global_normalized(2.0, normalized_A)
    meta = spec.metadata()
    assert meta["layer"] == "A_physical_ode_simulator"
    assert meta["mode"] == CouplingMode.GLOBAL_K_WITH_NORMALIZED_A.value
    assert meta["K"] == 2.0
    assert meta["scale_applied_once"] is True
    assert meta["claim_boundary"] == CLAIM_ATTRACTIVE
    assert meta["is_signed"] is False
    assert meta["has_negative_effective_edges"] is False


def test_metadata_flags_signed_negative_edges(normalized_A: np.ndarray) -> None:
    W = normalized_A.copy()
    W[1, 0] = -0.5
    meta = CouplingSpec.signed_weight(W).metadata()
    assert meta["is_signed"] is True
    assert meta["has_negative_effective_edges"] is True
    assert meta["claim_boundary"] == CLAIM_SIGNED


# ---------------------------------------------------------------------------
# Engine integration: coupling enters the dynamics exactly once
# ---------------------------------------------------------------------------


def test_from_coupling_spec_applies_scale_exactly_once(
    normalized_A: np.ndarray,
) -> None:
    """``KuramotoConfig.from_coupling_spec`` pins ``K=1`` so the engine's
    ``K · adjacency`` reproduces the effective matrix with no second scaling."""
    K = 3.0
    spec = CouplingSpec.global_normalized(K, normalized_A)
    cfg = KuramotoConfig.from_coupling_spec(spec, seed=0)

    assert cfg.K == 1.0
    assert cfg.adjacency is not None
    # Engine computes adj = cfg.K * cfg.adjacency = 1.0 * C = C.
    engine_effective = cfg.K * cfg.adjacency
    np.testing.assert_allclose(engine_effective, spec.effective_matrix(), atol=1e-12)
    # And C equals K·A applied once — not K²·A.
    expected = K * normalized_A
    np.fill_diagonal(expected, 0.0)
    np.testing.assert_allclose(engine_effective, expected, atol=1e-12)


def test_from_coupling_spec_rejects_non_spec() -> None:
    with pytest.raises(TypeError, match="CouplingSpec"):
        KuramotoConfig.from_coupling_spec(np.ones((3, 3)))
