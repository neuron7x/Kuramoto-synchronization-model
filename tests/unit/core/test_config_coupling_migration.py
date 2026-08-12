# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Migration guard for the legacy ``KuramotoConfig(K, adjacency)`` coupling path.

:class:`core.kuramoto.coupling_spec.CouplingSpec` already enforces *coupling
appears exactly once* at the spec layer. This module closes the remaining
**config-layer** bypass: the bare ``(K, adjacency)`` constructor cannot tell a
normalized topology ``A`` (``C = K·A``, scale intended) from an already-physical
weight matrix ``W`` (``C = W``), so passing ``W`` with a non-unit ``K`` silently
double-scales (``C = K·W``).

The guard requires the caller to declare ``adjacency_kind`` whenever ``K != 1.0``:

* ``adjacency_kind='full_weight'`` + ``K != 1.0`` is **rejected** (would double-scale);
* an **undeclared** convention + ``K != 1.0`` is **rejected fail-closed** (FP-1 residual
  double-scale hole, closed post-#1143: the ambiguity must not pass silently);
* ``KuramotoConfig.from_coupling_spec(...)`` is the canonical, scale-once path;
* a signed/repulsive coupling can never advertise the attractive-Kuramoto boundary.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.coupling_spec import CLAIM_ATTRACTIVE, CLAIM_SIGNED, CouplingSpec


def _normalized_topology(n: int = 4) -> np.ndarray:
    """Row-normalized non-negative topology with zero diagonal."""
    rng = np.random.default_rng(11)
    a = rng.uniform(0.0, 1.0, size=(n, n))
    np.fill_diagonal(a, 0.0)
    a /= a.sum(axis=1, keepdims=True)
    return np.asarray(a, dtype=np.float64)


def test_undeclared_adjacency_kind_with_nonunit_K_is_rejected() -> None:
    """Undeclared convention with K != 1.0 is rejected fail-closed (no silent double-scale).

    FP-1 residual hole (closed post-#1143): a caller passing a physical weight matrix W with
    K != 1.0 and no ``adjacency_kind`` would have C = K·W double-scaled. The constructor cannot
    distinguish a normalized topology A from a physical weight matrix W, so the only sound
    behaviour is to reject the ambiguity rather than warn-and-continue.
    """
    a = _normalized_topology()
    with pytest.raises(ValueError, match="ambiguous and is rejected fail-closed"):
        KuramotoConfig(N=a.shape[0], K=2.0, adjacency=a)


def test_from_coupling_spec_applies_scale_exactly_once() -> None:
    """The canonical path scales once and pins K to 1.0, with no warning."""
    a = _normalized_topology()
    spec = CouplingSpec.global_normalized(K=2.0, A=a)
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any spurious warning would fail here
        cfg = KuramotoConfig.from_coupling_spec(spec)

    assert cfg.K == 1.0
    assert cfg.adjacency_kind == "full_weight"
    expected = spec.effective_matrix()  # C = 2·A, diagonal zeroed, scaled once
    assert cfg.adjacency is not None
    np.testing.assert_allclose(cfg.adjacency, expected)
    # The engine computes K·adjacency = 1.0·C = C: the scale is not applied twice.
    np.testing.assert_allclose(cfg.K * np.asarray(cfg.adjacency), expected)


def test_full_weight_matrix_requires_unit_k() -> None:
    """A full physical weight matrix rejects any non-unit K (anti-double-scale)."""
    w = _normalized_topology()
    with pytest.raises(ValueError, match="must be exactly 1.0"):
        KuramotoConfig(N=w.shape[0], K=2.0, adjacency=w, adjacency_kind="full_weight")

    # K == 1.0 with a declared full-weight matrix is the accepted form.
    cfg = KuramotoConfig(N=w.shape[0], K=1.0, adjacency=w, adjacency_kind="full_weight")
    assert cfg.adjacency_kind == "full_weight"


def test_signed_coupling_cannot_claim_attractive_kuramoto() -> None:
    """Negative (repulsive) coupling can never carry the attractive claim boundary."""
    w = _normalized_topology()
    w_signed = w.copy()
    w_signed[0, 1] = -0.5  # introduce a repulsive edge

    # A signed CouplingSpec propagates the signed boundary through the config.
    spec = CouplingSpec.signed_weight(w_signed)
    cfg_signed = KuramotoConfig.from_coupling_spec(spec)
    assert cfg_signed.claim_boundary == CLAIM_SIGNED

    # Asserting the attractive boundary over negative edges is rejected outright.
    with pytest.raises(ValueError, match="forbids negative coupling weights"):
        KuramotoConfig(
            N=w_signed.shape[0],
            K=1.0,
            adjacency=w_signed,
            adjacency_kind="full_weight",
            claim_boundary=CLAIM_ATTRACTIVE,
        )

    # The signed boundary admits the same matrix.
    cfg = KuramotoConfig(
        N=w_signed.shape[0],
        K=1.0,
        adjacency=w_signed,
        adjacency_kind="full_weight",
        claim_boundary=CLAIM_SIGNED,
    )
    assert cfg.claim_boundary == CLAIM_SIGNED


def test_declared_normalized_topology_is_silent_and_scales_in_engine() -> None:
    """Explicitly declaring a normalized topology keeps C = K·A and emits no warning."""
    a = _normalized_topology()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        cfg = KuramotoConfig(
            N=a.shape[0], K=3.0, adjacency=a, adjacency_kind="normalized_topology"
        )
    assert cfg.K == 3.0
    assert cfg.adjacency_kind == "normalized_topology"
    assert cfg.adjacency is not None
    np.testing.assert_allclose(np.asarray(cfg.adjacency), a)


def test_declared_normalized_topology_with_nonunit_K_constructs() -> None:
    """No false-positive: declaring 'normalized_topology' with K != 1.0 constructs cleanly.

    Companion to ``test_undeclared_adjacency_kind_with_nonunit_K_is_rejected``: the fail-closed
    rejection fires only on the *undeclared* ambiguity. Once the caller declares the convention,
    the same (K != 1.0, adjacency) pair is admissible and C = K·A is the intended single scaling.
    """
    a = _normalized_topology()
    cfg = KuramotoConfig(N=a.shape[0], K=2.0, adjacency=a, adjacency_kind="normalized_topology")
    assert cfg.K == 2.0
    assert cfg.adjacency_kind == "normalized_topology"
    assert cfg.adjacency is not None
    np.testing.assert_allclose(np.asarray(cfg.adjacency), a)


def test_unit_k_with_adjacency_needs_no_declaration() -> None:
    """With K == 1.0 there is no scaling ambiguity, so no declaration is required."""
    a = _normalized_topology()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        cfg = KuramotoConfig(N=a.shape[0], K=1.0, adjacency=a)
    assert cfg.adjacency_kind is None


def test_invalid_claim_boundary_rejected() -> None:
    """Only the two canonical claim-boundary strings are accepted."""
    a = _normalized_topology()
    with pytest.raises(ValueError, match="claim_boundary must be one of"):
        KuramotoConfig(N=a.shape[0], K=1.0, adjacency=a, claim_boundary="anything_goes")
