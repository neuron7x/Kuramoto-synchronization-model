# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical data contracts for the NetworkKuramotoEngine inverse-problem stack.

This module defines every dataclass that crosses a boundary between the
phase-extraction, coupling-estimation, delay-estimation, frustration-
estimation, simulation, and metrics stages of the Sakaguchi–Kuramoto
identification pipeline described in ``KURAMOTO_NETWORK_ENGINE_METHODOLOGY.md``
(protocol M1.1).

Design principles
-----------------
1. **Frozen + slots** on every dataclass. ``frozen=True`` blocks attribute
   reassignment; ``slots=True`` reduces per-instance overhead and disables
   the instance ``__dict__`` for the fields (subclass fields only).
2. **Deep immutability** for ``np.ndarray`` fields via
   :class:`_FrozenArrayMixin`. ``frozen=True`` alone does not prevent
   mutation of array *contents*; the mixin takes a defensive copy and sets
   ``flags.writeable = False`` on every array field in ``__post_init__``.
3. **Shape, dtype and range validation** is expressed declaratively by
   overriding ``_validate`` in each subclass. ``_validate`` runs *after*
   the arrays have been frozen, so invariants are checked on the stored
   (immutable) values.
4. **Shared vocabulary** — ``asset_ids`` is a ``tuple[str, ...]`` (hashable,
   immutable) on every contract so that matrices can be indexed consistently
   across stages of the pipeline.

These contracts are the single source of truth consumed by
``phase_extractor.py``, ``coupling_estimator.py``, ``delay_estimator.py``,
``frustration.py``, ``network_engine.py``, ``metrics.py``, ``falsification.py``
and the ``NetworkKuramotoFeature`` adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import numpy as np

__all__ = [
    "PhaseMatrix",
    "CouplingMatrix",
    "DelayMatrix",
    "FrustrationMatrix",
    "NetworkState",
    "EmergentMetrics",
    "SyntheticGroundTruth",
]


# ---------------------------------------------------------------------------
# Immutability primitives
# ---------------------------------------------------------------------------


def _freeze_array(arr: np.ndarray | None) -> np.ndarray | None:
    """Return a defensively copied, write-protected view of ``arr``.

    ``frozen=True`` dataclasses prevent attribute reassignment but the
    *contents* of an ``np.ndarray`` remain mutable: the caller could still
    write into the buffer and silently corrupt downstream state. This helper
    breaks that path by (a) taking a private copy so the caller cannot retain
    a writable alias, and (b) clearing ``flags.writeable`` so any in-place
    mutation on the stored array raises ``ValueError``.

    ``None`` is forwarded unchanged so that optional fields (e.g.
    ``CouplingMatrix.stability_scores``) can remain absent.
    """
    if arr is None:
        return None
    out = np.array(arr, copy=True)
    out.flags.writeable = False
    return out


class _FrozenArrayMixin:
    """Mixin that deep-freezes every ``np.ndarray`` field on construction.

    Concrete dataclasses declare fields as usual; this mixin iterates
    :func:`dataclasses.fields` inside ``__post_init__``, replaces each
    array with its write-protected copy via :func:`_freeze_array`, and
    then dispatches to :meth:`_validate` for subclass-specific invariant
    checks. Using ``object.__setattr__`` bypasses the ``frozen=True``
    assignment guard, which is the only sanctioned mutation path on a
    frozen dataclass.

    Subclasses override :meth:`_validate`; the mixin itself enforces no
    shape or range constraints, so it is reusable across every contract.
    """

    __slots__ = ()

    def __post_init__(self) -> None:
        for f in fields(self):  # type: ignore[arg-type]
            val = getattr(self, f.name)
            if isinstance(val, np.ndarray):
                object.__setattr__(self, f.name, _freeze_array(val))
        self._validate()

    def _validate(self) -> None:  # pragma: no cover - overridden
        """Hook for subclass-level invariant checks. Default: no-op."""


# ---------------------------------------------------------------------------
# Helper validators
# ---------------------------------------------------------------------------


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _check_square(name: str, arr: np.ndarray, n: int) -> None:
    _require(
        arr.ndim == 2 and arr.shape == (n, n),
        f"{name} must have shape ({n}, {n}); got {arr.shape}",
    )


def _check_finite(name: str, arr: np.ndarray) -> None:
    _require(bool(np.all(np.isfinite(arr))), f"{name} contains NaN or Inf values")


# ---------------------------------------------------------------------------
# Phase extraction output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PhaseMatrix(_FrozenArrayMixin):
    """Instantaneous phase ``θ_i(t)`` for ``N`` oscillators over ``T`` steps.

    Attributes
    ----------
    theta : np.ndarray
        Shape ``(T, N)``, dtype ``float64``. Values normalised into
        ``[0, 2π)``. The consumer is responsible for calling
        ``np.unwrap`` before any derivative/regression step — the stored
        phases are wrapped so that the representation is canonical.
    timestamps : np.ndarray
        Shape ``(T,)``, monotonically increasing. Dtype is unconstrained
        (``float64`` epoch seconds and ``datetime64[ns]`` both allowed).
    asset_ids : tuple[str, ...]
        Length ``N``, unique identifiers. Used to align columns across
        downstream matrices.
    extraction_method : str
        One of ``{"hilbert", "ceemdan", "ssq_cwt"}``.
    frequency_band : tuple[float, float]
        ``(f_low, f_high)`` in cycles per sample unit (caller-defined;
        cycles/day for daily bars, cycles/minute for minute bars).
    amplitude : np.ndarray | None
        Optional analytic-signal amplitude ``|z_i(t)|``, same shape as
        ``theta``. Used by the quality gates and as a confidence weight
        for the coupling estimator.
    quality_scores : dict[str, float] | None
        Per-asset / per-gate quality diagnostics populated by the
        extractor (e.g. ``{"Q1_low_amp_fraction": 0.03, ...}``).
    """

    theta: np.ndarray
    timestamps: np.ndarray
    asset_ids: tuple[str, ...]
    extraction_method: str
    frequency_band: tuple[float, float]
    amplitude: np.ndarray | None = None
    quality_scores: dict[str, float] | None = None

    _ALLOWED_METHODS: tuple[str, ...] = ("hilbert", "ceemdan", "ssq_cwt")

    def _validate(self) -> None:
        _require(self.theta.ndim == 2, f"theta must be 2-D; got {self.theta.ndim}")
        t, n = self.theta.shape
        _require(t >= 2, f"theta must have ≥2 timesteps; got T={t}")
        _require(n >= 1, f"theta must have ≥1 oscillator; got N={n}")
        _require(
            self.theta.dtype == np.float64,
            f"theta must be float64; got {self.theta.dtype}",
        )
        _check_finite("theta", self.theta)
        _require(
            float(self.theta.min()) >= 0.0 and float(self.theta.max()) < 2.0 * np.pi,
            "theta must be wrapped to [0, 2π)",
        )
        _require(
            self.timestamps.shape == (t,),
            f"timestamps shape must be ({t},); got {self.timestamps.shape}",
        )
        _require(
            len(self.asset_ids) == n,
            f"len(asset_ids)={len(self.asset_ids)} must equal N={n}",
        )
        _require(
            len(set(self.asset_ids)) == n,
            "asset_ids must be unique",
        )
        _require(
            self.extraction_method in self._ALLOWED_METHODS,
            f"extraction_method must be one of {self._ALLOWED_METHODS}",
        )
        f_low, f_high = self.frequency_band
        _require(
            0.0 <= f_low < f_high,
            f"frequency_band must satisfy 0 ≤ f_low < f_high; got {self.frequency_band}",
        )
        if self.amplitude is not None:
            _require(
                self.amplitude.shape == self.theta.shape,
                f"amplitude shape {self.amplitude.shape} != theta shape {self.theta.shape}",
            )
            _require(
                bool(np.all(self.amplitude >= 0.0)),
                "amplitude must be non-negative",
            )

    @property
    def T(self) -> int:
        """Number of timesteps."""
        return int(self.theta.shape[0])

    @property
    def N(self) -> int:
        """Number of oscillators."""
        return int(self.theta.shape[1])


# ---------------------------------------------------------------------------
# Coupling estimation output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CouplingMatrix(_FrozenArrayMixin):
    """Signed coupling strengths ``K_ij`` between oscillators.

    ``K`` is **not** forced symmetric. Competitive or predator–prey
    dynamics (sector rotation, risk-on/risk-off pairs) legitimately
    produce antisymmetric edges, so the estimator only emits warnings
    rather than symmetrising.
    """

    K: np.ndarray
    asset_ids: tuple[str, ...]
    sparsity: float
    method: str
    stability_scores: np.ndarray | None = None
    confidence_intervals: np.ndarray | None = None

    _ALLOWED_METHODS: tuple[str, ...] = (
        "scad",
        "mcp",
        "lasso",
        "graphical_lasso",
        "fused_glasso",
    )

    def _validate(self) -> None:
        n = len(self.asset_ids)
        _check_square("K", self.K, n)
        _require(self.K.dtype == np.float64, f"K must be float64; got {self.K.dtype}")
        _check_finite("K", self.K)
        _require(
            bool(np.all(np.diag(self.K) == 0.0)),
            "K diagonal must be zero (no self-coupling)",
        )
        _require(
            0.0 <= self.sparsity <= 1.0,
            f"sparsity must be in [0,1]; got {self.sparsity}",
        )
        _require(
            self.method in self._ALLOWED_METHODS,
            f"method must be one of {self._ALLOWED_METHODS}",
        )
        if self.stability_scores is not None:
            _check_square("stability_scores", self.stability_scores, n)
            _require(
                float(self.stability_scores.min()) >= 0.0
                and float(self.stability_scores.max()) <= 1.0,
                "stability_scores must lie in [0, 1]",
            )
        if self.confidence_intervals is not None:
            _require(
                self.confidence_intervals.shape == (n, n, 2),
                f"confidence_intervals shape must be ({n},{n},2)",
            )

    @property
    def N(self) -> int:
        return int(self.K.shape[0])

    def nonzero_mask(self) -> np.ndarray:
        """Boolean mask of active edges (``|K_ij| > 0``)."""
        return np.asarray(self.K != 0.0, dtype=bool)


# ---------------------------------------------------------------------------
# Delay estimation output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DelayMatrix(_FrozenArrayMixin):
    """Propagation delays ``τ_ij`` in integer timesteps and seconds."""

    tau: np.ndarray
    tau_seconds: np.ndarray
    asset_ids: tuple[str, ...]
    method: str
    max_lag_tested: int

    _ALLOWED_METHODS: tuple[str, ...] = (
        "cross_correlation",
        "hry",
        "pcmci",
        "profile_likelihood",
        "consensus",
    )

    def _validate(self) -> None:
        n = len(self.asset_ids)
        _check_square("tau", self.tau, n)
        _check_square("tau_seconds", self.tau_seconds, n)
        _require(
            bool(np.issubdtype(self.tau.dtype, np.integer)),
            f"tau must have integer dtype; got {self.tau.dtype}",
        )
        _require(bool(np.all(self.tau >= 0)), "tau must be non-negative")
        _require(bool(np.all(np.diag(self.tau) == 0)), "tau diagonal must be zero")
        _require(
            int(self.tau.max(initial=0)) <= self.max_lag_tested,
            "tau exceeds max_lag_tested",
        )
        _require(
            self.method in self._ALLOWED_METHODS,
            f"method must be one of {self._ALLOWED_METHODS}",
        )
        _require(self.max_lag_tested >= 0, "max_lag_tested must be ≥ 0")


# ---------------------------------------------------------------------------
# Phase frustration output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FrustrationMatrix(_FrozenArrayMixin):
    """Sakaguchi phase frustration ``α_ij`` ∈ [-π, π]."""

    alpha: np.ndarray
    asset_ids: tuple[str, ...]
    method: str

    _ALLOWED_METHODS: tuple[str, ...] = (
        "circular_regression",
        "bayesian",
        "steady_state",
        "profile_likelihood",
    )

    def _validate(self) -> None:
        n = len(self.asset_ids)
        _check_square("alpha", self.alpha, n)
        _require(
            self.alpha.dtype == np.float64,
            f"alpha must be float64; got {self.alpha.dtype}",
        )
        _check_finite("alpha", self.alpha)
        _require(
            float(np.abs(self.alpha).max(initial=0.0)) <= np.pi + 1e-9,
            "alpha must lie in [-π, π]",
        )
        _require(
            self.method in self._ALLOWED_METHODS,
            f"method must be one of {self._ALLOWED_METHODS}",
        )


# ---------------------------------------------------------------------------
# Aggregate network state
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NetworkState(_FrozenArrayMixin):
    """Complete identified state of a Sakaguchi–Kuramoto network.

    This is the container that the simulation engine consumes (via
    ``SE.1``) and the feature adapter caches between batch recalibrations.
    All component matrices must share the same ``asset_ids`` ordering.
    """

    phases: PhaseMatrix
    coupling: CouplingMatrix
    delays: DelayMatrix
    frustration: FrustrationMatrix
    natural_frequencies: np.ndarray
    noise_std: float

    def _validate(self) -> None:
        n = self.phases.N
        ids = self.phases.asset_ids
        _require(
            self.coupling.asset_ids == ids
            and self.delays.asset_ids == ids
            and self.frustration.asset_ids == ids,
            "asset_ids must be identical across phases, coupling, delays, frustration",
        )
        _require(
            self.natural_frequencies.shape == (n,),
            f"natural_frequencies shape must be ({n},)",
        )
        _require(
            self.natural_frequencies.dtype == np.float64,
            "natural_frequencies must be float64",
        )
        _check_finite("natural_frequencies", self.natural_frequencies)
        _require(self.noise_std >= 0.0, "noise_std must be ≥ 0")

    @property
    def N(self) -> int:
        return self.phases.N

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return self.phases.asset_ids


# ---------------------------------------------------------------------------
# Emergent metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmergentMetrics(_FrozenArrayMixin):
    """Derived emergent-dynamics metrics computed from a ``NetworkState``."""

    R_global: np.ndarray
    R_cluster: dict[int, np.ndarray]
    metastability: float
    chimera_index: np.ndarray
    csd_variance: np.ndarray
    csd_autocorr: np.ndarray
    edge_entropy: float
    cluster_assignments: np.ndarray

    def _validate(self) -> None:
        _require(self.R_global.ndim == 1, "R_global must be 1-D")
        t = self.R_global.shape[0]
        _require(
            float(self.R_global.min(initial=0.0)) >= -1e-9
            and float(self.R_global.max(initial=0.0)) <= 1.0 + 1e-9,
            "R_global must lie in [0, 1]",
        )
        _require(self.chimera_index.shape == (t,), "chimera_index shape mismatch")
        _require(self.csd_variance.shape == (t,), "csd_variance shape mismatch")
        _require(self.csd_autocorr.shape == (t,), "csd_autocorr shape mismatch")
        _require(self.metastability >= 0.0, "metastability must be ≥ 0")
        _require(self.edge_entropy >= 0.0, "edge_entropy must be ≥ 0")
        _require(
            self.cluster_assignments.ndim == 1,
            "cluster_assignments must be 1-D",
        )
        _require(
            np.issubdtype(self.cluster_assignments.dtype, np.integer),
            "cluster_assignments must be integer-valued",
        )
        for c, r in self.R_cluster.items():
            _require(isinstance(c, (int, np.integer)), "R_cluster keys must be int")
            _require(
                r.ndim == 1 and r.shape[0] == t,
                f"R_cluster[{c}] must have shape ({t},)",
            )


# ---------------------------------------------------------------------------
# Synthetic ground truth
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SyntheticGroundTruth(_FrozenArrayMixin):
    """Known-parameter Sakaguchi–Kuramoto data for recovery tests (M3.1)."""

    true_K: np.ndarray
    true_tau: np.ndarray
    true_alpha: np.ndarray
    true_omega: np.ndarray
    generated_phases: PhaseMatrix
    noise_realizations: np.ndarray
    metadata: dict[str, Any] | None = None

    def _validate(self) -> None:
        n = self.generated_phases.N
        _check_square("true_K", self.true_K, n)
        _check_square("true_tau", self.true_tau, n)
        _check_square("true_alpha", self.true_alpha, n)
        _require(
            self.true_omega.shape == (n,),
            f"true_omega shape must be ({n},); got {self.true_omega.shape}",
        )
        _require(bool(np.all(np.diag(self.true_K) == 0.0)), "true_K diagonal must be zero")
        _require(bool(np.all(np.diag(self.true_tau) == 0)), "true_tau diagonal must be zero")
        _require(bool(np.all(self.true_tau >= 0)), "true_tau must be non-negative")
        _require(
            float(np.abs(self.true_alpha).max(initial=0.0)) <= np.pi + 1e-9,
            "true_alpha must lie in [-π, π]",
        )
