# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed synchronization-manifold frame over a causal snapshot.

:class:`SynchronizationManifoldFrame` is a *descriptor frame*, not a Kuramoto
solver. It wraps the order parameter computed by the already-shipped
``core.kuramoto.metrics.order_parameter`` and the Lyapunov regime label from
``core.physics.lyapunov_spectrum`` into a typed object that refuses to record a
physically impossible synchronization state:

* an order parameter outside ``R ∈ [0, 1]`` (INV-K1),
* a *subcritical* ensemble (``K < K_c``) whose steady-state ``R`` sits above the
  finite-size noise floor ``3/√N`` after the declared horizon
  (catalog ``kuramoto.subcritical_finite_size``),
* a *supercritical* ensemble (``K > K_c``) with no order above that floor
  (catalog ``kuramoto.frequency_entrainment`` — locking must raise ``R``),
* phase data contaminated by future L2 (a ``VIOLATED`` causal-cutoff status),
* a missing oscillator count ``N`` or critical coupling ``K_c``.

No Kuramoto dynamics are integrated here; the frame only binds and bounds the
descriptors the existing engine/metrics produce.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.metrics import order_parameter
from physics_contracts.manifold.contracts import CausalCutoffStatus, canonical_digest

__all__ = [
    "SynchronizationManifoldFrame",
    "finite_size_floor_for",
    "build_sync_frame",
]

# Lorentzian finite-size constant: ⟨R⟩ ≲ C/√N below threshold, witness bound
# ``r < 3/√N`` (catalog kuramoto.subcritical_finite_size). 3 is the law's own
# coefficient, not a magic number.
_FINITE_SIZE_COEFF: Final[float] = 3.0

_LYAPUNOV_REGIMES: Final[frozenset[str]] = frozenset({"stable", "neutral", "chaotic", "unknown"})


def _is_finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


def finite_size_floor_for(n_oscillators: int) -> float:
    """Finite-size noise floor ``3/√N`` (catalog kuramoto.subcritical_finite_size)."""

    if n_oscillators < 1:
        raise ValueError(
            "kuramoto.subcritical_finite_size VIOLATED: N must be >= 1 to define a finite-size floor"
        )
    return _FINITE_SIZE_COEFF / (float(n_oscillators) ** 0.5)


@dataclass(frozen=True, slots=True)
class SynchronizationManifoldFrame:
    """A synchronization descriptor frame bound to a causal snapshot.

    The frame validates the structural Kuramoto bounds fail-closed. The
    regime-conditioned falsifiers (subcritical floor, supercritical locking)
    require the coupling context and are enforced by :func:`build_sync_frame`,
    which records the resulting ``R`` here only once it is admissible.
    """

    snapshot_id: str
    R: float
    finite_size_floor: float
    phase_dispersion: float
    locked_fraction: float
    lyapunov_regime: str
    causal_cutoff_status: CausalCutoffStatus
    validity_domain: str

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ValueError(
                "manifold.provenance_replay_identity VIOLATED: frame has empty snapshot_id"
            )
        if not (0.0 <= self.R <= 1.0):
            raise ValueError(f"INV-K1 VIOLATED: order parameter R={self.R} outside [0, 1]")
        if not _is_finite(self.finite_size_floor) or self.finite_size_floor < 0.0:
            raise ValueError(
                "kuramoto.subcritical_finite_size VIOLATED: finite_size_floor "
                f"{self.finite_size_floor!r} must be finite and non-negative"
            )
        if not _is_finite(self.phase_dispersion) or self.phase_dispersion < 0.0:
            raise ValueError(
                f"SynchronizationManifoldFrame VIOLATED: phase_dispersion "
                f"{self.phase_dispersion!r} must be finite and non-negative"
            )
        if not (0.0 <= self.locked_fraction <= 1.0):
            raise ValueError(
                f"kuramoto.frequency_entrainment VIOLATED: locked_fraction "
                f"{self.locked_fraction} outside [0, 1]"
            )
        if self.lyapunov_regime not in _LYAPUNOV_REGIMES:
            raise ValueError(
                f"SynchronizationManifoldFrame VIOLATED: lyapunov_regime "
                f"{self.lyapunov_regime!r} not in {sorted(_LYAPUNOV_REGIMES)}"
            )
        # Phase data computed on look-ahead-contaminated L2 is inadmissible.
        if self.causal_cutoff_status is CausalCutoffStatus.VIOLATED:
            raise ValueError(
                "manifold.causal_cutoff VIOLATED: synchronization frame built on phase data "
                "with a VIOLATED causal cutoff (future L2 leaked into the phases) — rejected"
            )
        if not self.validity_domain:
            raise ValueError("SynchronizationManifoldFrame VIOLATED: validity_domain is empty")

    @property
    def frame_digest(self) -> str:
        """Deterministic content-address of the frame (replay identity)."""

        return canonical_digest(
            {
                "snapshot_id": self.snapshot_id,
                "R": self.R,
                "finite_size_floor": self.finite_size_floor,
                "phase_dispersion": self.phase_dispersion,
                "locked_fraction": self.locked_fraction,
                "lyapunov_regime": self.lyapunov_regime,
                "causal_cutoff_status": self.causal_cutoff_status.value,
                "validity_domain": self.validity_domain,
            }
        )


def _steady_state_R(theta: NDArray[np.float64]) -> float:
    """Mean order parameter over the final-quarter (post-horizon) window."""

    R_series = order_parameter(theta, axis=1)
    horizon = max(1, R_series.shape[0] // 4)
    return float(np.mean(R_series[-horizon:]))


def build_sync_frame(
    *,
    snapshot_id: str,
    theta: NDArray[np.float64],
    coupling_K: float,
    critical_K: float,
    n_oscillators: int,
    locked_fraction: float,
    lyapunov_regime: str,
    validity_domain: str,
    causal_cutoff_status: CausalCutoffStatus = CausalCutoffStatus.VALID,
) -> SynchronizationManifoldFrame:
    """Build a fail-closed :class:`SynchronizationManifoldFrame` from phases.

    ``theta`` is a ``(T, N)`` phase trajectory the existing Kuramoto engine
    produced. The steady-state ``R`` is the post-horizon mean of
    ``order_parameter(theta)``; ``N`` and ``K_c`` are required (a frame with no
    declared critical coupling cannot be regime-checked and is refused).

    Regime falsifiers (fail-closed):

    * ``K < K_c`` (subcritical) with ``R`` above ``3/√N`` ⇒ ``ValueError``.
    * ``K > K_c`` (supercritical) with ``R`` at or below ``3/√N`` ⇒ ``ValueError``.
    """

    if n_oscillators < 1:
        raise ValueError(
            "kuramoto.subcritical_finite_size VIOLATED: missing/invalid N "
            f"({n_oscillators}); cannot define the finite-size floor"
        )
    if not _is_finite(critical_K) or critical_K <= 0.0:
        raise ValueError(
            f"kuramoto.frequency_entrainment VIOLATED: missing/invalid critical coupling "
            f"K_c={critical_K!r} (must be a positive float)"
        )
    if not _is_finite(coupling_K) or coupling_K < 0.0:
        raise ValueError(
            f"SynchronizationManifoldFrame VIOLATED: invalid coupling K={coupling_K!r}"
        )

    floor = finite_size_floor_for(n_oscillators)
    R = _steady_state_R(theta)

    if coupling_K < critical_K and R > floor:
        raise ValueError(
            "kuramoto.subcritical_finite_size VIOLATED: K<K_c "
            f"({coupling_K} < {critical_K}) but steady R={R:.4f} > finite-size floor "
            f"3/√N={floor:.4f}; subcritical order must stay at the noise floor"
        )
    if coupling_K > critical_K and R <= floor:
        raise ValueError(
            "kuramoto.frequency_entrainment VIOLATED: K>K_c "
            f"({coupling_K} > {critical_K}) but steady R={R:.4f} ≤ finite-size floor "
            f"3/√N={floor:.4f}; supercritical coupling must raise the order parameter"
        )

    # Circular standard deviation at the final frame: σ = √(−2 ln R̄). A pure
    # descriptor over the existing order parameter, no new dynamics.
    R_final = max(min(R, 1.0), 1e-12)
    phase_dispersion = float((-2.0 * np.log(R_final)) ** 0.5)

    return SynchronizationManifoldFrame(
        snapshot_id=snapshot_id,
        R=R,
        finite_size_floor=floor,
        phase_dispersion=phase_dispersion,
        locked_fraction=locked_fraction,
        lyapunov_regime=lyapunov_regime,
        causal_cutoff_status=causal_cutoff_status,
        validity_domain=validity_domain,
    )
