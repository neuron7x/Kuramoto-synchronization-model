# SPDX-License-Identifier: MIT
"""Mathematical witness for law ``kuramoto_ricci.semantics_split`` (FP-2 / INV-KR4).

Runtime-layer witness binding the physics_contracts catalog law to executable
checks. Pairs with the assistant-layer falsification battery in
``tests/unit/physics/test_KR4_ricci_semantics_split.py``; both layers move
together (issue #1096 Lane B).

The law: signed Ollivier-Ricci curvature is never silently destroyed. The
positive path clips negatives ONLY with audit metadata; the signed path
preserves every negative value; a signed matrix at the Restrepo-Ott-Hunt onset
boundary is rejected fail-closed.
"""

from __future__ import annotations

import jax.numpy as jnp
import numpy as np
import pytest
from jax import Array

from core.kuramoto.kuramoto_ricci_engine import (
    assert_roh_compatible,
    phase_transition_boundary,
    ricci_to_positive_adjacency,
    ricci_to_signed_coupling,
)
from physics_contracts.law import law

# The signed-preservation check is exact arithmetic; allow only float round-off.
SIGN_PRESERVE_TOLERANCE = 1e-12


def _signed_kappa() -> Array:
    """Symmetric κ with negatives summing to |mass| = 0.6 (edges (0,2)=(2,0)=−0.3)."""
    return jnp.asarray(
        np.array(
            [
                [0.0, 0.5, -0.3],
                [0.5, 0.0, 0.2],
                [-0.3, 0.2, 0.0],
            ],
            dtype=np.float64,
        )
    )


@law("kuramoto_ricci.semantics_split")
def test_positive_path_clips_only_with_audit() -> None:
    """The threshold path discards negative curvature ONLY with explicit audit."""
    kappa = _signed_kappa()
    adjacency, audit = ricci_to_positive_adjacency(kappa)

    sym_off = 0.5 * (np.asarray(kappa) + np.asarray(kappa).T)
    np.fill_diagonal(sym_off, 0.0)
    expected_neg_edges = int(np.sum(sym_off < 0.0))
    expected_neg_mass = float(np.sum(np.abs(np.minimum(sym_off, 0.0))))

    assert audit.clipped_for_threshold is (expected_neg_edges > 0), (
        "INV-KR4: clipped_for_threshold must equal (#negative_edges > 0); the "
        "clip may never be silent."
    )
    assert audit.negative_edges_count == expected_neg_edges
    assert abs(audit.negative_mass - expected_neg_mass) < SIGN_PRESERVE_TOLERANCE
    assert audit.roh_compatible is True
    assert audit.signed_dynamics_compatible is False
    assert bool(jnp.all(adjacency >= 0.0))


@law("kuramoto_ricci.semantics_split")
def test_signed_path_preserves_every_negative_bit() -> None:
    """The signed path retains every κ_ij < 0 bit-for-bit (no silent loss)."""
    kappa = _signed_kappa()
    coupling, audit = ricci_to_signed_coupling(kappa)

    sym = 0.5 * (np.asarray(kappa) + np.asarray(kappa).T)
    np.fill_diagonal(sym, 0.0)
    np.testing.assert_allclose(np.asarray(coupling), sym, atol=SIGN_PRESERVE_TOLERANCE)
    assert bool(jnp.any(coupling < 0.0)), "INV-KR4: signed coupling lost its negatives."
    assert audit.signed_dynamics_compatible is True
    assert audit.roh_compatible is False
    assert audit.clipped_for_threshold is False


@law("kuramoto_ricci.semantics_split")
def test_signed_matrix_rejected_at_onset_boundary() -> None:
    """A signed coupling at the ROH boundary fails closed (fail-closed predicate)."""
    signed, _ = ricci_to_signed_coupling(_signed_kappa())
    with pytest.raises(ValueError, match="INV-KR4"):
        assert_roh_compatible(signed)
    with pytest.raises(ValueError):
        phase_transition_boundary(1.0, 0.1, signed)
