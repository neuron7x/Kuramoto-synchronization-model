# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable falsification witnesses for ricci_semantics_split (INV-KR4, FP-2).

Law ``ricci_kuramoto.semantics_split`` (issue #1096 Lane B): signed Ollivier-Ricci
curvature is NEVER silently destroyed. Two named engine paths keep the loss-or-
preservation of sign explicit, and a signed matrix can never be silently fed where
non-negativity (Restrepo-Ott-Hunt onset compatibility) is required:

* ``ricci_to_positive_adjacency`` — clips negative κ to zero ONLY here and ONLY
  with :class:`RicciAdjacencyAudit` metadata (``clipped_for_threshold=True``,
  ``negative_edges_count>0``, ``negative_mass>0``, ``roh_compatible=True``).
* ``ricci_to_signed_coupling`` — preserves every negative value bit-for-bit
  (``roh_compatible=False``, ``signed_dynamics_compatible=True``); carries NO
  onset-threshold claim.

These witnesses CALL the real engine (no reimplementation). The positive witness
proves sign is preserved on the signed path and clipped-with-audit on the positive
path; the negative control proves a signed matrix is rejected fail-closed at the
ROH boundary and that ``roh_compatible`` and ``signed_dynamics_compatible`` are
mutually exclusive whenever negatives are present — so silent destruction is
impossible.
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
    ricci_to_positive_adjacency,
    ricci_to_signed_coupling,
)


def _signed_kappa() -> Array:
    """Symmetric κ with two off-diagonal negatives, |negative_mass| = 0.6.

    Edges: (0,1)=+0.5, (0,2)=−0.3, (1,2)=+0.2. The symmetrised matrix carries the
    two negative entries (0,2) and (2,0), so ``negative_edges_count == 2`` and
    ``negative_mass == |−0.3| + |−0.3| == 0.6``.
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


def test_signed_curvature_split_preserves_and_audits() -> None:
    """Positive witness: signed path PRESERVES every negative; positive path CLIPS with audit.

    INV-KR4: the signed descriptor keeps each κ_ij < 0 bit-for-bit and disclaims the
    ROH onset (``roh_compatible=False``); the threshold path discards exactly that
    negative mass but ONLY with audit metadata recording the loss.
    """
    kappa = _signed_kappa()

    # Signed path: every negative value survives, sign is preserved, no ROH claim.
    signed, signed_audit = ricci_to_signed_coupling(kappa)
    assert isinstance(signed_audit, RicciAdjacencyAudit)
    sym = 0.5 * (np.asarray(kappa) + np.asarray(kappa).T)
    np.fill_diagonal(sym, 0.0)
    n_negative = int(np.sum(sym < 0.0))
    negative_mass = float(np.sum(np.where(sym < 0.0, np.abs(sym), 0.0)))
    preserved = bool(jnp.all(jnp.asarray(np.asarray(signed) == sym)))
    assert preserved and signed_audit.roh_compatible is False, (
        f"INV-KR4 VIOLATED: signed Ricci curvature was not preserved bit-for-bit "
        f"(preserved={preserved}) or wrongly claimed ROH compatibility "
        f"(roh_compatible={signed_audit.roh_compatible}, expected False). "
        f"ricci_to_signed_coupling must keep all {n_negative} negative edges "
        f"(negative_mass={negative_mass:.3f}) with signed_dynamics_compatible=True; "
        f"atol=0 exact, N={sym.shape[0]} symmetric κ from _signed_kappa()."
    )
    assert signed_audit.clipped_for_threshold is False
    assert signed_audit.signed_dynamics_compatible is True

    # Positive path: negatives clipped, but ONLY with full audit metadata present.
    positive, pos_audit = ricci_to_positive_adjacency(kappa)
    clipped_clean = bool(jnp.all(positive >= 0.0))
    assert (
        clipped_clean
        and pos_audit.clipped_for_threshold is True
        and pos_audit.negative_edges_count == n_negative
        and pos_audit.negative_mass > 0.0
        and pos_audit.roh_compatible is True
    ), (
        f"INV-KR4 VIOLATED: positive path either left a negative entry "
        f"(non_negative={clipped_clean}) or clipped WITHOUT audit metadata "
        f"(clipped_for_threshold={pos_audit.clipped_for_threshold}, "
        f"negative_edges_count={pos_audit.negative_edges_count} expected {n_negative}, "
        f"negative_mass={pos_audit.negative_mass:.3f} expected >0, "
        f"roh_compatible={pos_audit.roh_compatible} expected True). The clip is only "
        f"admissible when the discarded mass is MEASURED (no silent destruction)."
    )
    assert abs(pos_audit.negative_mass - negative_mass) < 1e-9
    assert pos_audit.signed_dynamics_compatible is False


def test_signed_curvature_rejected_at_roh_boundary_fail_closed() -> None:
    """Negative control: a signed matrix is rejected fail-closed at the ROH onset boundary.

    This is the discriminating falsifier — if negatives could be silently fed where
    roh-compatibility is required, ``assert_roh_compatible`` and
    ``phase_transition_boundary`` would return a meaningless Φ instead of raising.
    It also pins the mutual exclusivity of the two compatibility bits when negatives
    are present, proving silent destruction is structurally impossible.
    """
    kappa = _signed_kappa()
    signed, signed_audit = ricci_to_signed_coupling(kappa)
    _, pos_audit = ricci_to_positive_adjacency(kappa)

    # 1) assert_roh_compatible is the fail-closed guard: signed κ → ValueError.
    with pytest.raises(ValueError, match="INV-KR4"):
        assert_roh_compatible(signed)

    # 2) The ROH boundary itself refuses a signed matrix (defence in depth via the
    #    INV-KR3 non-negativity guard) — no silent Φ is ever produced.
    with pytest.raises(ValueError):
        phase_transition_boundary(1.0, 0.1, signed)

    # 3) Mutual exclusivity when negatives are present: never both ROH-compatible
    #    AND signed-dynamics-compatible on one matrix (the category error the split
    #    exists to forbid), and the two paths disagree on each compatibility bit.
    assert signed_audit.negative_edges_count > 0
    assert not (
        signed_audit.roh_compatible and signed_audit.signed_dynamics_compatible
    ), (
        "INV-KR4 VIOLATED: a signed matrix claimed BOTH ROH-threshold compatibility "
        "AND signed-dynamics compatibility — silent destruction of sign would be "
        "possible. roh_compatible and signed_dynamics_compatible must be mutually "
        f"exclusive when negatives are present (negative_edges_count="
        f"{signed_audit.negative_edges_count})."
    )
    assert signed_audit.roh_compatible != pos_audit.roh_compatible
    assert (
        signed_audit.signed_dynamics_compatible
        != pos_audit.signed_dynamics_compatible
    )
