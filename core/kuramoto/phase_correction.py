# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Forced-Kuramoto phase correction toward a baseline phase reference.

Implements the canonical forced-Kuramoto correction step

    dθ_i/dt = K · sin(θ_ref_i − θ_i)

as a pure-functional NumPy primitive. Each oscillator is pulled
toward its corresponding reference phase by a sinusoidal coupling
of strength ``K``. Converges to ``θ = θ_ref`` for any finite
initial phase set when ``K > 0`` and the explicit-Euler stability
bound ``dt < 2 / K`` is respected.

What this is *not*
------------------

* Not a "reset wave" in any neurological sense — that name was a
  decoration. The mechanism is forced Kuramoto with a phase
  reference; the literature term is *Kuramoto-Sakaguchi with
  phase-locked driver* or *forced-oscillator network*. We use
  the honest term in the public API.
* Not parameterised by "serotonin gain" — the multiplier is
  a coupling strength ``K`` with units of inverse time. Calling
  it serotonin would imply a connection to
  :mod:`core.neuro.serotonin_ode` that does not exist in this
  module.
* Not coupled to E/I balance, dissociation, or homeostatic
  stabiliser state — those belong to
  :mod:`geosync.neuroeconomics.homeostatic_stabilizer`. This
  module is the **physics primitive**; the stabiliser is the
  **policy** that uses it.

Public surface
--------------

* :func:`wrap_to_pi` — fold any real array to ``[-π, π]``.
* :func:`circular_phase_distance` — modular phase distance, the
  only honest definition for circular variables.
* :class:`KuramotoCorrectionReport` — frozen per-step report:
  velocity norm, potential energy, max phase error, n_nodes.
* :func:`kuramoto_correction_step` — single forced-Kuramoto Euler
  step toward a reference; returns ``(new_phases, report)``.
* :func:`reset_to_baseline` — iterates the step until max phase
  error falls below tolerance or max iterations are reached;
  returns the trajectory.

Invariants enforced
-------------------

* **INV-K-CORR1** (universal, P0): output phases lie in ``[-π, π]``
  after every step (modular wrap).
* **INV-K-CORR2** (monotonic, P0): the Kuramoto potential
  ``V = Σ (1 − cos(θ_ref − θ))`` is non-increasing across an
  Euler step when ``K · dt < 2`` (explicit-Euler stability bound).
* **INV-K-CORR3** (asymptotic, P1): under the stability bound,
  ``max |θ_ref − θ| → 0`` exponentially with rate ``K``.

References
----------

* Kuramoto, Y. (1984). *Chemical Oscillations, Waves, and
  Turbulence.* Springer.
* Sakaguchi, H., Kuramoto, Y. (1986). A soluble active rotator
  model showing phase transitions via mutual entrainment. *Prog.
  Theor. Phys.* 76, 576.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "KuramotoCorrectionReport",
    "KuramotoResetTrajectory",
    "circular_phase_distance",
    "kuramoto_correction_step",
    "reset_to_baseline",
    "wrap_to_pi",
]


def wrap_to_pi(phases: NDArray[np.float64]) -> NDArray[np.float64]:
    """Fold phases to the interval ``[-π, π]``.

    Vectorised. Pure. Idempotent on already-wrapped inputs to
    machine precision.
    """
    return ((phases + math.pi) % (2.0 * math.pi)) - math.pi


def circular_phase_distance(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Element-wise circular distance ``|a − b|`` modulo 2π.

    Returned values lie in ``[0, π]`` — the shortest arc on the
    unit circle. This is the *only* honest distance for phase
    variables; ``abs(a − b)`` is wrong by construction near the
    ``±π`` wrap-around.
    """
    return np.abs(wrap_to_pi(a - b))


@dataclass(frozen=True, slots=True)
class KuramotoCorrectionReport:
    """Per-step report from :func:`kuramoto_correction_step`.

    Attributes
    ----------
    velocity_norm:
        :math:`\\| K \\sin(\\theta_{ref} - \\theta) \\|_2` — Euclidean
        norm of the per-node correction velocity. The honest
        Kuramoto sync gradient. Goes to zero at the fixed point.
    potential_energy:
        :math:`V = \\sum_i (1 - \\cos(\\theta_{ref,i} - \\theta_i))`.
        Bounded ``[0, 2N]``. Zero iff every phase matches its
        reference. Non-increasing across an Euler step under the
        stability bound — INV-K-CORR2.
    max_phase_error:
        :math:`\\max_i |\\theta_{ref,i} - \\theta_i|_{\\text{circular}}`
        in ``[0, π]``. The L∞ residual. The convergence verdict
        uses this — strictly more conservative than the mean.
    n_nodes:
        Number of oscillators in the population.
    """

    velocity_norm: float
    potential_energy: float
    max_phase_error: float
    n_nodes: int


@dataclass(frozen=True, slots=True)
class KuramotoResetTrajectory:
    """Output of :func:`reset_to_baseline` — full iteration trace.

    Attributes
    ----------
    final_phases:
        Phases after the last iteration, wrapped to ``[-π, π]``.
    iterations_run:
        Number of Euler steps actually executed (≤ ``max_iters``).
    converged:
        ``True`` iff ``final_report.max_phase_error <=
        convergence_tol``. Derived, not asserted.
    final_report:
        :class:`KuramotoCorrectionReport` from the last step.
    potential_history:
        Length-``iterations_run + 1`` array of the potential
        energy at each step (including the initial state). Used
        to falsify INV-K-CORR2 monotonicity.
    """

    final_phases: NDArray[np.float64]
    iterations_run: int
    converged: bool
    final_report: KuramotoCorrectionReport
    potential_history: NDArray[np.float64]


def _validate_phase_inputs(
    phases: NDArray[np.float64],
    baseline_phases: NDArray[np.float64],
) -> None:
    if phases.shape != baseline_phases.shape:
        raise ValueError(
            "phases and baseline_phases must share shape; "
            f"got {phases.shape} vs {baseline_phases.shape}."
        )
    if phases.ndim != 1:
        raise ValueError(f"expected 1-D arrays, got ndim={phases.ndim}.")
    if phases.size == 0:
        raise ValueError("at least one node phase is required.")
    if not (np.isfinite(phases).all() and np.isfinite(baseline_phases).all()):
        raise ValueError(
            "INV-HPC2: phases and baseline_phases must be all-finite; fail-closed at the boundary."
        )


def kuramoto_correction_step(
    phases: NDArray[np.float64],
    baseline_phases: NDArray[np.float64],
    *,
    coupling: float,
    dt: float,
) -> tuple[NDArray[np.float64], KuramotoCorrectionReport]:
    """Single forced-Kuramoto Euler step toward a baseline phase reference.

    Update rule:

    .. math::
        \\theta_i \\leftarrow \\mathrm{wrap}\\!\\big(\\theta_i + dt
            \\cdot K \\sin(\\theta_{ref,i} - \\theta_i)\\big).

    Stability bound for explicit Euler: ``coupling * dt < 2``.
    Beyond this, the discrete update can over-shoot and the
    potential may oscillate rather than monotonically decrease.

    Parameters
    ----------
    phases:
        Current phases as a 1-D ``float64`` array. Will be wrapped
        to ``[-π, π]`` on output.
    baseline_phases:
        Target phase reference, same shape as ``phases``.
    coupling:
        Strictly positive coupling strength ``K``.
    dt:
        Strictly positive integration step.

    Raises
    ------
    ValueError
        On shape / ndim / non-finite / non-positive coupling
        violations.
    """
    if not math.isfinite(coupling) or coupling <= 0.0:
        raise ValueError(f"coupling must be a finite positive number; got {coupling!r}.")
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError(f"dt must be a finite positive number; got {dt!r}.")
    _validate_phase_inputs(phases, baseline_phases)

    diff = wrap_to_pi(baseline_phases - phases)
    velocity = coupling * np.sin(diff)
    new_phases = wrap_to_pi(phases + dt * velocity)

    # Recompute the residual against the NEW phases — the report is
    # the post-step snapshot.
    new_diff = wrap_to_pi(baseline_phases - new_phases)
    potential = float(np.sum(1.0 - np.cos(new_diff)))
    velocity_norm = float(np.linalg.norm(coupling * np.sin(new_diff)))
    max_error = float(np.max(np.abs(new_diff)))

    return new_phases, KuramotoCorrectionReport(
        velocity_norm=velocity_norm,
        potential_energy=potential,
        max_phase_error=max_error,
        n_nodes=int(phases.size),
    )


def reset_to_baseline(
    phases: NDArray[np.float64],
    baseline_phases: NDArray[np.float64],
    *,
    coupling: float,
    dt: float,
    max_iters: int = 200,
    convergence_tol: float = 1e-3,
) -> KuramotoResetTrajectory:
    """Iterate forced-Kuramoto correction until convergence or budget exhausted.

    Stops when ``max_phase_error < convergence_tol`` (success) or
    when ``max_iters`` is reached (budget exhaustion). The returned
    trajectory carries the full potential history so a caller can
    falsify INV-K-CORR2 monotonicity directly.

    The default ``convergence_tol = 1e-3`` is **not** a magic number:
    it sets the L∞ residual at one milliradian, which is below the
    reading precision of any production phase estimator we know of.
    Callers that need a tighter floor should pass it explicitly.

    Parameters
    ----------
    phases, baseline_phases:
        Initial and target phase arrays.
    coupling, dt:
        Forced-Kuramoto coupling and integration step. Must
        satisfy ``coupling * dt < 2`` for monotone convergence
        under explicit Euler.
    max_iters:
        Hard cap on iterations. Default 200 — sufficient at
        ``K = 1.0, dt = 0.1`` for any initial misalignment in
        ``[-π, π]`` to fall below ``1e-3`` empirically.
    convergence_tol:
        L∞ residual threshold (in radians) below which the
        trajectory is declared converged.
    """
    if max_iters <= 0:
        raise ValueError(f"max_iters must be > 0; got {max_iters!r}.")
    if not math.isfinite(convergence_tol) or convergence_tol <= 0.0:
        raise ValueError(
            f"convergence_tol must be a finite positive number; got {convergence_tol!r}."
        )
    _validate_phase_inputs(phases, baseline_phases)

    current = wrap_to_pi(np.asarray(phases, dtype=np.float64))
    initial_diff = wrap_to_pi(baseline_phases - current)
    initial_potential = float(np.sum(1.0 - np.cos(initial_diff)))
    potentials: list[float] = [initial_potential]

    last_report = KuramotoCorrectionReport(
        velocity_norm=float(np.linalg.norm(coupling * np.sin(initial_diff))),
        potential_energy=initial_potential,
        max_phase_error=float(np.max(np.abs(initial_diff))),
        n_nodes=int(current.size),
    )
    iters_done = 0
    for i in range(1, max_iters + 1):
        current, last_report = kuramoto_correction_step(
            current, baseline_phases, coupling=coupling, dt=dt
        )
        potentials.append(last_report.potential_energy)
        iters_done = i
        if last_report.max_phase_error < convergence_tol:
            break

    return KuramotoResetTrajectory(
        final_phases=current,
        iterations_run=iters_done,
        converged=last_report.max_phase_error < convergence_tol,
        final_report=last_report,
        potential_history=np.asarray(potentials, dtype=np.float64),
    )
