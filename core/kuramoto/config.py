# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Configuration and parameter validation for the Kuramoto simulation engine."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .coupling_spec import CLAIM_ATTRACTIVE, CLAIM_SIGNED


class KuramotoConfig(BaseModel):
    """Validated configuration for deterministic Kuramoto simulations.

    Coupling semantics:
    - ``adjacency is None``: global all-to-all coupling with per-edge weight ``K/N``.
    - ``adjacency is not None``: explicit weighted topology with effective weight ``K*A_ij``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    N: int = Field(default=10, ge=2, description="Number of oscillators (≥ 2)")
    K: float = Field(default=1.0, description="Global coupling strength scale")
    omega: np.ndarray | None = Field(
        default=None,
        description="Natural frequencies [rad/time]; length N. Drawn from N(0,1) if None.",
    )
    dt: float = Field(default=0.01, gt=0.0, description="Integration time-step (must be > 0)")
    steps: int = Field(default=1000, ge=1, description="Number of integration steps (≥ 1)")
    adjacency: np.ndarray | None = Field(
        default=None,
        description=(
            "Optional N×N weighted coupling matrix. Diagonal values are accepted but ignored "
            "during integration (no-self-coupling)."
        ),
    )
    adjacency_kind: Literal["normalized_topology", "full_weight"] | None = Field(
        default=None,
        description=(
            "Declares how 'adjacency' relates to the effective coupling C summed in the ODE, "
            "closing the silent double-scaling path. 'normalized_topology': adjacency is a "
            "topology A that K scales (C = K·A); any K is admissible. 'full_weight': adjacency "
            "already carries physical magnitudes (C = adjacency); K must be 1.0. None: the "
            "convention is undeclared — admissible only when K == 1.0 (no ambiguity); with "
            "K != 1.0 it is rejected fail-closed because C = K·adjacency may double-scale. "
            "Prefer KuramotoConfig.from_coupling_spec(...)."
        ),
    )
    claim_boundary: str = Field(
        default=CLAIM_ATTRACTIVE,
        description=(
            "What may be asserted about the dynamics. Attractive coupling (K ≥ 0, weights ≥ 0) "
            "carries the standard synchronization theorems; signed/repulsive coupling cannot. "
            "Propagated from CouplingSpec by from_coupling_spec()."
        ),
    )
    legacy_pre_scaled_adjacency: bool = Field(
        default=False,
        description=(
            "FP-1 back-compatibility switch. When False (default, canonical "
            "single-owner-of-scale): 'adjacency' is topology A_norm only and the "
            "engine applies the gain K once in the RHS — θ̇_i = ω_i + K·Σ_j "
            "A_norm[i,j]·sin(θ_j−θ_i). When True: 'adjacency' is treated as the "
            "already-K-scaled effective coupling C = K·A and the RHS uses unit "
            "gain, reproducing the pre-FP-1 trajectory bit-for-bit for external "
            "callers that pre-multiplied their matrix by K. New code should leave "
            "this False."
        ),
    )
    theta0: np.ndarray | None = Field(
        default=None,
        description="Initial phases [rad]; length N. Drawn from U(0, 2π) if None.",
    )
    seed: int | None = Field(default=None, description="Integer RNG seed for reproducibility.")

    @model_validator(mode="after")
    def _validate_arrays(self) -> KuramotoConfig:
        """Validate scalar constraints and array shapes/finiteness."""
        N = self.N

        if not np.isfinite(self.K):
            raise ValueError("'K' must be finite.")
        if self.seed is not None and self.seed < 0:
            raise ValueError("'seed' must be >= 0 when provided.")

        if self.omega is not None:
            omega = np.asarray(self.omega, dtype=np.float64)
            if omega.ndim != 1 or omega.shape[0] != N:
                raise ValueError(
                    f"'omega' must be a 1-D array of length N={N}; got shape {omega.shape}."
                )
            if not np.isfinite(omega).all():
                raise ValueError("'omega' contains non-finite values (NaN or Inf).")
            object.__setattr__(self, "omega", omega)

        if self.theta0 is not None:
            theta0 = np.asarray(self.theta0, dtype=np.float64)
            if theta0.ndim != 1 or theta0.shape[0] != N:
                raise ValueError(
                    f"'theta0' must be a 1-D array of length N={N}; got shape {theta0.shape}."
                )
            if not np.isfinite(theta0).all():
                raise ValueError("'theta0' contains non-finite values (NaN or Inf).")
            object.__setattr__(self, "theta0", theta0)

        if self.adjacency is not None:
            adj = np.asarray(self.adjacency, dtype=np.float64)
            if adj.ndim != 2 or adj.shape != (N, N):
                raise ValueError(
                    f"'adjacency' must be an (N×N)=({N}×{N}) matrix; got shape {adj.shape}."
                )
            if not np.isfinite(adj).all():
                raise ValueError("'adjacency' contains non-finite values (NaN or Inf).")
            object.__setattr__(self, "adjacency", adj)

        self._enforce_coupling_convention()
        self._enforce_claim_boundary()
        return self

    def _enforce_coupling_convention(self) -> None:
        """Close the silent double-scaling path of the bare ``(K, adjacency)`` ctor.

        The effective coupling summed in the ODE is ``C = K · adjacency``. If
        ``adjacency`` is a *normalized topology* ``A`` this is the intended
        ``C = K·A``; if it is already a *physical weight matrix* ``W`` the extra
        ``K`` double-scales (``C = K·W``). The constructor cannot tell ``A`` from
        ``W`` by inspection, so the caller must declare which via
        ``adjacency_kind`` whenever ``K != 1.0``. ``from_coupling_spec`` is the
        canonical path and sets this automatically.
        """
        if self.adjacency is None or self.K == 1.0:
            # K == 1.0 ⇒ C = adjacency regardless of convention; no ambiguity.
            return
        if self.adjacency_kind == "full_weight":
            raise ValueError(
                "adjacency_kind='full_weight' means 'adjacency' already carries physical "
                f"coupling magnitudes (C = adjacency); the scalar K must be exactly 1.0 to "
                f"avoid double-scaling (C = K·W). Got K={self.K!r}. Declare "
                "adjacency_kind='normalized_topology' if K is meant to scale the matrix, or "
                "build via KuramotoConfig.from_coupling_spec(...)."
            )
        if self.adjacency_kind is None:
            raise ValueError(
                "KuramotoConfig(K != 1.0, adjacency=...) with undeclared adjacency_kind is "
                f"ambiguous and is rejected fail-closed (got K={self.K!r}): if 'adjacency' is a "
                "normalized topology A the intent is C = K·A, but if it is already a physical "
                "weight matrix W then C = K·W double-scales the coupling, and the constructor "
                "cannot tell A from W by inspection. Declare adjacency_kind='normalized_topology' "
                "(K scales the matrix, C = K·A) or adjacency_kind='full_weight' (matrix already "
                "carries magnitudes, requires K=1.0), or build via "
                "KuramotoConfig.from_coupling_spec(...)."
            )

    def _enforce_claim_boundary(self) -> None:
        """A signed/repulsive coupling can never claim attractive Kuramoto physics."""
        if self.claim_boundary not in (CLAIM_ATTRACTIVE, CLAIM_SIGNED):
            raise ValueError(
                f"claim_boundary must be one of {CLAIM_ATTRACTIVE!r} or {CLAIM_SIGNED!r}; "
                f"got {self.claim_boundary!r}."
            )
        if self.claim_boundary != CLAIM_ATTRACTIVE:
            return
        if self.K < 0.0:
            raise ValueError(
                f"claim_boundary={CLAIM_ATTRACTIVE!r} forbids a negative global K "
                f"(repulsive); got K={self.K!r}. Declare claim_boundary={CLAIM_SIGNED!r}."
            )
        if self.adjacency is not None:
            min_w = float(np.asarray(self.adjacency, dtype=np.float64).min())
            if min_w < 0.0:
                raise ValueError(
                    f"claim_boundary={CLAIM_ATTRACTIVE!r} forbids negative coupling weights "
                    f"(found min {min_w:.6g}); signed/repulsive coupling must declare "
                    f"claim_boundary={CLAIM_SIGNED!r}."
                )

    @classmethod
    def from_coupling_spec(
        cls,
        spec: Any,
        *,
        omega: np.ndarray | None = None,
        dt: float = 0.01,
        steps: int = 1000,
        theta0: np.ndarray | None = None,
        seed: int | None = None,
    ) -> KuramotoConfig:
        """Build a config whose coupling is scaled exactly once.

        ``spec`` is a :class:`core.kuramoto.coupling_spec.CouplingSpec`. Its
        :meth:`~core.kuramoto.coupling_spec.CouplingSpec.effective_matrix` —
        the matrix in which the scale has already been applied once — is stored
        as ``adjacency`` with ``K`` pinned to ``1.0``. The engine then computes
        ``K · adjacency = 1.0 · C = C``, so the coupling strength enters the
        dynamics exactly once. This closes the double-scaling path that the bare
        ``(K, adjacency)`` constructor leaves open.
        """
        from .coupling_spec import CouplingSpec

        if not isinstance(spec, CouplingSpec):
            raise TypeError(f"from_coupling_spec expects a CouplingSpec; got {type(spec).__name__}")
        effective = spec.effective_matrix()
        return cls(
            N=spec.n_oscillators,
            K=1.0,
            omega=omega,
            dt=dt,
            steps=steps,
            adjacency=effective,
            adjacency_kind="full_weight",
            claim_boundary=spec.claim_boundary,
            theta0=theta0,
            seed=seed,
        )

    @property
    def coupling_mode(self) -> str:
        """Return active coupling semantics label for summaries/serialization."""
        return "adjacency" if self.adjacency is not None else "global"

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a deterministic, JSON-compatible dictionary."""
        return {
            "N": self.N,
            "K": self.K,
            "omega": self.omega.tolist() if self.omega is not None else None,
            "dt": self.dt,
            "steps": self.steps,
            "adjacency": self.adjacency.tolist() if self.adjacency is not None else None,
            "adjacency_kind": self.adjacency_kind,
            "claim_boundary": self.claim_boundary,
            "legacy_pre_scaled_adjacency": self.legacy_pre_scaled_adjacency,
            "theta0": self.theta0.tolist() if self.theta0 is not None else None,
            "seed": self.seed,
            "coupling_mode": self.coupling_mode,
        }
