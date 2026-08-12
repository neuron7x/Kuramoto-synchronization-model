# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical coupling representation for the Kuramoto ODE (Stream 1 contract).

The Kuramoto right-hand side is

    dθ_i/dt = ω_i + Σ_j C_ij · sin(θ_j − θ_i)

where ``C`` is the *effective* coupling matrix actually summed in the
derivative. Across the stack the same physical coupling is expressed in two
incompatible conventions:

* a **global scalar** ``K`` multiplying a **normalized topology** ``A``
  (``C = K · A``), and
* a **full weight matrix** ``W`` whose magnitudes are already physical
  (``C = W``, with no further scaling).

:class:`KuramotoConfig` documents — but does not enforce — that ``adjacency``
is multiplied by ``K`` (``C = K · A``). Nothing stops a caller from passing a
matrix that is *already* a physical weight matrix ``W`` (for example the output
of :mod:`core.kuramoto.coupling_estimator`) while *also* setting a non-unit
scalar ``K``. The result, ``C = K · W``, double-scales the coupling: the scale
enters the dynamics twice. The dynamics look plausible, the tests stay green,
and the reported coupling strength is silently wrong.

**First principle (CLAUDE.md / Stream 1): coupling appears exactly once.**

:class:`CouplingSpec` owns the representation. It records *which* convention is
in force, refuses the combinations that would double-scale or that mix signed
semantics with an attractive-physics claim, and exposes a single
:meth:`CouplingSpec.effective_matrix` in which the scale has been applied
exactly once. The accompanying :attr:`CouplingSpec.claim_boundary` states what
may legitimately be asserted about the resulting dynamics.

This is a Layer-A object (``physical_ode_simulator``): it speaks only about
oscillator coupling and its numerical accountability. It makes no market or
descriptor claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .contracts import _check_finite, _check_square, _require

__all__ = [
    "CouplingMode",
    "CouplingSpec",
    "CLAIM_ATTRACTIVE",
    "CLAIM_SIGNED",
]

# ---------------------------------------------------------------------------
# Claim boundaries (what may be asserted about the dynamics)
# ---------------------------------------------------------------------------

#: Attractive Kuramoto: K ≥ 0 and all coupling weights ≥ 0. The standard
#: synchronization theorems (INV-K2/K3, critical coupling K_c) apply.
CLAIM_ATTRACTIVE = "physical_attractive_kuramoto_only"

#: Signed / repulsive coupling: negative weights or negative global K present.
#: Attractive-regime theorems do NOT apply; this is a signed-dynamics claim.
CLAIM_SIGNED = "signed_or_repulsive_dynamics_only"


class CouplingMode(str, Enum):
    """The convention in which a coupling is expressed.

    The mode is part of the model: it fixes how the scale is applied and which
    claim boundary the dynamics may carry. It is not cosmetic metadata.
    """

    #: ``C = K · A``. Scalar ``K ≥ 0`` carries the scale; ``A ≥ 0`` is a
    #: (typically row-normalized) topology. Attractive claim boundary.
    GLOBAL_K_WITH_NORMALIZED_A = "global_k_with_normalized_a"

    #: ``C = W``. ``W ≥ 0`` already carries physical magnitudes; the scalar
    #: ``K`` is meaningless here and MUST equal 1.0 (anti-double-scaling).
    #: Attractive claim boundary.
    FULL_WEIGHT_MATRIX_W = "full_weight_matrix_w"

    #: ``C = W``. ``W`` may contain negative (repulsive) entries; ``K`` MUST
    #: equal 1.0. Signed claim boundary.
    SIGNED_POS_NEG_CHANNELS = "signed_pos_neg_channels"

    #: ``C = K · A``. ``K`` may be negative (global repulsion) and ``A`` may be
    #: signed. The only mode in which a negative ``K`` is admissible. Signed
    #: claim boundary.
    REPULSIVE_OR_SIGNED_MODE = "repulsive_or_signed_mode"


_SIGNED_MODES = frozenset(
    {CouplingMode.SIGNED_POS_NEG_CHANNELS, CouplingMode.REPULSIVE_OR_SIGNED_MODE}
)
#: Modes in which the matrix already carries physical magnitudes, so the scalar
#: ``K`` must be exactly 1.0 — applying it again would double-scale.
_UNIT_K_MODES = frozenset({CouplingMode.FULL_WEIGHT_MATRIX_W, CouplingMode.SIGNED_POS_NEG_CHANNELS})


@dataclass(frozen=True, slots=True)
class CouplingSpec:
    """A coupling matrix together with the convention that scales it.

    Construct via the classmethods (:meth:`global_normalized`,
    :meth:`full_weight`, :meth:`signed_weight`, :meth:`repulsive_global`) for
    readable call sites, or directly for full control. Validation runs in
    ``__post_init__`` and is fail-closed: every violation raises
    :class:`ValueError`, never a silent repair.

    Attributes
    ----------
    matrix:
        The coupling topology / weights, shape ``(N, N)``. Frozen on
        construction; the diagonal is *not* required to be zero (self-coupling
        is dropped by :meth:`effective_matrix`).
    mode:
        The :class:`CouplingMode` fixing how ``K`` is applied.
    K:
        Global scalar coupling strength. Must be ``1.0`` for full-weight modes.
    """

    matrix: NDArray[np.float64]
    mode: CouplingMode
    K: float = 1.0
    _frozen: NDArray[np.float64] = field(init=False, repr=False, compare=False)

    # -- construction helpers ------------------------------------------------

    @classmethod
    def global_normalized(cls, K: float, A: NDArray[np.float64]) -> CouplingSpec:
        """Attractive global coupling ``C = K · A`` with ``K ≥ 0``, ``A ≥ 0``."""
        return cls(matrix=A, mode=CouplingMode.GLOBAL_K_WITH_NORMALIZED_A, K=K)

    @classmethod
    def full_weight(cls, W: NDArray[np.float64]) -> CouplingSpec:
        """Attractive physical weights ``C = W`` (``W ≥ 0``); no global scale."""
        return cls(matrix=W, mode=CouplingMode.FULL_WEIGHT_MATRIX_W, K=1.0)

    @classmethod
    def signed_weight(cls, W: NDArray[np.float64]) -> CouplingSpec:
        """Signed physical weights ``C = W`` (negative entries allowed)."""
        return cls(matrix=W, mode=CouplingMode.SIGNED_POS_NEG_CHANNELS, K=1.0)

    @classmethod
    def repulsive_global(cls, K: float, A: NDArray[np.float64]) -> CouplingSpec:
        """Global signed coupling ``C = K · A`` permitting negative ``K``/``A``."""
        return cls(matrix=A, mode=CouplingMode.REPULSIVE_OR_SIGNED_MODE, K=K)

    # -- validation ----------------------------------------------------------

    def __post_init__(self) -> None:
        arr = np.asarray(self.matrix, dtype=np.float64)
        _require(arr.ndim == 2, f"coupling matrix must be 2-D; got ndim={arr.ndim}")
        n = arr.shape[0]
        _require(n >= 2, f"coupling matrix must be at least 2x2; got N={n}")
        _check_square("coupling matrix", arr, n)
        _check_finite("coupling matrix", arr)
        _require(
            isinstance(self.mode, CouplingMode),
            f"mode must be a CouplingMode; got {type(self.mode).__name__}",
        )
        _require(np.isfinite(self.K), "K must be finite")

        # Anti-double-scaling: a matrix that already carries physical
        # magnitudes must not be scaled again by a non-unit K.
        if self.mode in _UNIT_K_MODES:
            _require(
                self.K == 1.0,
                f"{self.mode.value} carries physical magnitudes; the scalar K "
                f"must be exactly 1.0 to avoid double-scaling (C = K·W). "
                f"Got K={self.K!r}. Pass the weights via a global mode if K is "
                f"meant to scale them.",
            )

        # Sign discipline: negative K only in the explicitly repulsive mode.
        if self.K < 0.0:
            _require(
                self.mode == CouplingMode.REPULSIVE_OR_SIGNED_MODE,
                f"negative K={self.K!r} is only admissible in "
                f"REPULSIVE_OR_SIGNED_MODE; mode {self.mode.value} is attractive "
                f"or signed-matrix and requires K ≥ 0.",
            )

        # Attractive modes forbid negative coupling weights.
        if self.mode not in _SIGNED_MODES:
            min_w = float(arr.min())
            _require(
                min_w >= 0.0,
                f"{self.mode.value} is attractive (claim boundary "
                f"{CLAIM_ATTRACTIVE!r}); all weights must be ≥ 0. Found "
                f"min weight {min_w:.6g}. Use a signed mode to admit "
                f"repulsive edges.",
            )

        frozen = np.array(arr, copy=True)
        frozen.flags.writeable = False
        object.__setattr__(self, "matrix", frozen)
        object.__setattr__(self, "_frozen", frozen)

    # -- derived quantities --------------------------------------------------

    @property
    def n_oscillators(self) -> int:
        """Number of oscillators ``N``."""
        return int(self._frozen.shape[0])

    @property
    def claim_boundary(self) -> str:
        """What may legitimately be claimed about dynamics under this coupling.

        Signed/repulsive modes can never return :data:`CLAIM_ATTRACTIVE`: the
        standard synchronization theorems do not hold once repulsion is present.
        """
        if self.mode in _SIGNED_MODES:
            return CLAIM_SIGNED
        return CLAIM_ATTRACTIVE

    def effective_matrix(self) -> NDArray[np.float64]:
        """Return ``C``, the coupling summed in the ODE, scaled exactly once.

        ``C = K · A`` for global modes and ``C = W`` for full-weight modes
        (where ``K`` is constrained to 1.0). The diagonal is zeroed — there is
        no self-coupling in the Kuramoto RHS — and the result is write-locked.
        """
        c = self._frozen * self.K if self.K != 1.0 else self._frozen.copy()
        np.fill_diagonal(c, 0.0)  # INV: no self-coupling in dθ_i/dt
        c.flags.writeable = False
        return c

    def metadata(self) -> dict[str, Any]:
        """Provenance record: how the coupling is scaled and what it may claim.

        Emitting this alongside any downstream artifact makes the scaling
        convention auditable and the claim boundary explicit.
        """
        eff = self.effective_matrix()
        return {
            "layer": "A_physical_ode_simulator",
            "mode": self.mode.value,
            "K": float(self.K),
            "N": self.n_oscillators,
            "scale_applied_once": True,
            "claim_boundary": self.claim_boundary,
            "is_signed": self.mode in _SIGNED_MODES,
            "has_negative_effective_edges": bool(eff.min() < 0.0),
            "effective_row_sum_max": float(np.abs(eff).sum(axis=1).max()),
        }
