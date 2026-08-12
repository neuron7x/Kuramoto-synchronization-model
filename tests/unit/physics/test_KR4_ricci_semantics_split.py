# SPDX-License-Identifier: MIT
"""Fail-closed battery for INV-KR4: Ricci positive/signed semantics split (FP-2).

Issue #1096 Lane B — "No silent physics loss". The Ollivier-Ricci κ-matrix
carries SIGNED information (κ_ij < 0 = anti-synchronising / repulsive edge). Two
named paths must keep the loss-or-preservation of that sign explicit:

* ``ricci_to_positive_adjacency`` — threshold/onset-safe, clips negatives ONLY
  here and ONLY with audit metadata (``clipped_for_threshold=True``).
* ``ricci_to_signed_coupling``    — preserves every negative value; carries NO
  ROH threshold claim.

INV-KR4 (P0) makes this fail-closed: a signed matrix sent to the Restrepo-Ott-
Hunt boundary is rejected, and signed curvature can never be silently discarded
while still claiming full physical dynamics. Each test pins one clause of the
contract; ``test_negative_control_*`` proves the positive tests are not vacuous.
"""

from __future__ import annotations

import jax.numpy as jnp
import numpy as np
import pytest
from jax import Array

from core.kuramoto.kuramoto_ricci_engine import (
    RicciAdjacencyAudit,
    assert_roh_compatible,
    phase_transition_boundary,
    ricci_to_adjacency,
    ricci_to_positive_adjacency,
    ricci_to_signed_coupling,
)


def _signed_kappa() -> Array:
    """Symmetric κ with two off-diagonal negatives summing to |mass| = 0.6.

    Edges: (0,1)=+0.5, (0,2)=−0.3, (1,2)=+0.2. The symmetric matrix has the two
    negative entries (0,2) and (2,0), so negative_edges_count == 2 and
    negative_mass == 0.6 (= |−0.3| + |−0.3|).
    """
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


def _all_positive_kappa() -> Array:
    """Symmetric κ with no negative off-diagonal entries (INV-KR4 negative control)."""
    return jnp.asarray(
        np.array(
            [
                [0.0, 0.5, 0.3],
                [0.5, 0.0, 0.2],
                [0.3, 0.2, 0.0],
            ],
            dtype=np.float64,
        )
    )


# ── INV-KR4: negative edges are AUDITED (not silently dropped) ────────────────


def test_ricci_negative_edges_audited() -> None:
    """INV-KR4: the positive path reports how many edges / how much mass it clips."""
    kappa = _signed_kappa()
    adjacency, audit = ricci_to_positive_adjacency(kappa)

    assert isinstance(audit, RicciAdjacencyAudit)
    assert audit.negative_edges_count == 2, (
        f"INV-KR4 VIOLATED: expected 2 negative off-diagonal edges in the "
        f"symmetrised κ, audit reported {audit.negative_edges_count}. The two "
        f"entries (0,2)=(2,0)=−0.3 must both be counted."
    )
    assert abs(audit.negative_mass - 0.6) < 1e-6, (
        f"INV-KR4 VIOLATED: negative curvature mass must be Σ|min(κ,0)| = 0.6 "
        f"(|−0.3|+|−0.3|), audit reported {audit.negative_mass}. The discarded "
        f"signed information must be measured, not hidden."
    )
    # The returned adjacency is genuinely non-negative (the clip happened).
    assert bool(jnp.all(adjacency >= 0.0)), (
        "INV-KR4 VIOLATED: ricci_to_positive_adjacency returned a negative entry; "
        "the threshold path must yield a non-negative (ROH-compatible) matrix."
    )


def test_ricci_positive_path_clips_only_with_metadata() -> None:
    """INV-KR4: ``clipped_for_threshold`` is True iff a negative edge was clipped."""
    _, audit_signed = ricci_to_positive_adjacency(_signed_kappa())
    assert audit_signed.clipped_for_threshold is True
    assert audit_signed.roh_compatible is True
    assert audit_signed.signed_dynamics_compatible is False, (
        "INV-KR4 VIOLATED: the clipped positive matrix must NOT claim "
        "signed-dynamics compatibility — its negative curvature is gone."
    )

    _, audit_clean = ricci_to_positive_adjacency(_all_positive_kappa())
    assert audit_clean.clipped_for_threshold is False, (
        "INV-KR4 VIOLATED: an all-positive κ has nothing to clip, so "
        "clipped_for_threshold must be False (no false-positive audit)."
    )
    assert audit_clean.negative_edges_count == 0
    assert audit_clean.negative_mass == 0.0


def test_signed_ricci_preserves_negative_values() -> None:
    """INV-KR4: the signed path keeps every negative curvature (full descriptor)."""
    kappa = _signed_kappa()
    coupling, audit = ricci_to_signed_coupling(kappa)

    assert bool(jnp.any(coupling < 0.0)), (
        "INV-KR4 VIOLATED: ricci_to_signed_coupling DROPPED the negative "
        "curvature — signed physics was silently lost while the path claims "
        "to preserve the full signed descriptor."
    )
    # Sign-preserving means the off-diagonal equals the symmetrised input.
    sym = 0.5 * (np.asarray(kappa) + np.asarray(kappa).T)
    np.fill_diagonal(sym, 0.0)
    np.testing.assert_allclose(np.asarray(coupling), sym, atol=1e-12)
    assert audit.clipped_for_threshold is False
    assert audit.signed_dynamics_compatible is True
    assert audit.roh_compatible is False


def test_roh_boundary_rejects_signed_matrix() -> None:
    """INV-KR4: a signed coupling sent to the ROH boundary fails closed (no silent Φ)."""
    signed, _ = ricci_to_signed_coupling(_signed_kappa())

    with pytest.raises(ValueError, match="INV-KR4"):
        assert_roh_compatible(signed)

    # The boundary itself must also reject it (defence in depth: the existing
    # INV-KR3 non-negativity guard is the second fail-closed layer).
    with pytest.raises(ValueError):
        phase_transition_boundary(1.0, 0.1, signed)


def test_signed_dynamics_does_not_claim_roh_threshold() -> None:
    """INV-KR4: the signed audit disclaims the ROH threshold; positive asserts it."""
    _, signed_audit = ricci_to_signed_coupling(_signed_kappa())
    _, positive_audit = ricci_to_positive_adjacency(_signed_kappa())

    # The two paths are mutually exclusive on the onset claim whenever negatives
    # are present: one is ROH-safe and one is signed-dynamics-safe, never both.
    assert signed_audit.roh_compatible != positive_audit.roh_compatible
    assert (
        signed_audit.signed_dynamics_compatible
        != positive_audit.signed_dynamics_compatible
    )
    assert not (
        signed_audit.roh_compatible and signed_audit.signed_dynamics_compatible
    ), (
        "INV-KR4 VIOLATED: a single matrix claimed BOTH ROH-threshold "
        "compatibility AND signed-dynamics compatibility — that is the exact "
        "category error the split exists to prevent."
    )


def test_positive_path_roh_compatible_accepted_by_boundary() -> None:
    """INV-KR4: positive completeness — the clipped matrix is genuinely ROH-usable."""
    positive, _ = ricci_to_positive_adjacency(_signed_kappa())
    assert_roh_compatible(positive)  # must not raise
    report = phase_transition_boundary(1.0, 0.1, positive)
    assert np.isfinite(report.phi)
    assert report.lambda_max_A >= 0.0


def test_backcompat_alias_matches_positive_path() -> None:
    """INV-KR4: ``ricci_to_adjacency`` is the positive path without the audit."""
    kappa = _signed_kappa()
    legacy = np.asarray(ricci_to_adjacency(kappa))
    positive, _ = ricci_to_positive_adjacency(kappa)
    np.testing.assert_array_equal(legacy, np.asarray(positive))


# ── Negative control: the audit MUST react to changed input ───────────────────


def test_negative_control_all_positive_kappa_audit_reports_no_loss() -> None:
    """INV-KR4: if κ has no negatives, BOTH paths agree there was nothing to lose.

    This is the falsifier for a vacuous audit: were the audit hard-coded to
    report a clip, this all-positive input would wrongly trip it.
    """
    _, pos_audit = ricci_to_positive_adjacency(_all_positive_kappa())
    signed, sig_audit = ricci_to_signed_coupling(_all_positive_kappa())

    assert pos_audit.negative_edges_count == 0
    assert pos_audit.clipped_for_threshold is False
    assert sig_audit.negative_edges_count == 0
    # With no negatives the signed coupling is itself non-negative, so it is
    # numerically ROH-usable even though its audit declares no onset claim.
    assert bool(jnp.all(signed >= 0.0))
    assert_roh_compatible(signed)  # all-positive ⇒ no fail-closed trip
