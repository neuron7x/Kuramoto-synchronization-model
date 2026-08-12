# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Detrended Fluctuation Analysis γ estimator — robust on non-stationary data.

Algorithm (Peng et al. 1994):
  1. Profile: y(k) = Σ(x_i - mean)
  2. Divide into windows of size s
  3. Detrend each window (linear fit)
  4. F(s) = sqrt(mean residual variance)
  5. H = slope of log F(s) vs log s
  6. γ = 2H + 1 (DERIVED, never assigned)

Cross-validation: Daubechies db4 wavelet detail coefficients
yield independent H estimate via variance scaling.

Advantage over Welch PSD: no stationarity assumption.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from enum import Enum

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class DFAEstimate:
    """DFA gamma estimate with wavelet cross-validation.

    INV: abs(gamma - (2*hurst_exponent + 1)) < 1e-10
    """

    hurst_exponent: float
    gamma: float  # = 2*hurst_exponent + 1, NEVER assigned directly
    dfa_fluctuations: tuple[float, ...]
    scale_range: tuple[int, int]
    r_squared: float
    wavelet_confirmed: bool
    n_samples: int
    computation_time_ms: float

    def __post_init__(self) -> None:
        expected = 2.0 * self.hurst_exponent + 1.0
        if abs(self.gamma - expected) > 1e-10:
            raise ValueError(
                f"γ={self.gamma} ≠ 2H+1={expected}. gamma must be DERIVED from hurst_exponent."
            )


def _invalid_estimate(n: int, elapsed_ms: float) -> DFAEstimate:
    return DFAEstimate(
        hurst_exponent=0.0,
        gamma=1.0,  # 2*0.0+1
        dfa_fluctuations=(),
        scale_range=(0, 0),
        r_squared=0.0,
        wavelet_confirmed=False,
        n_samples=n,
        computation_time_ms=elapsed_ms,
    )


class DFAGammaEstimator:
    """Detrended Fluctuation Analysis for non-stationary series.

    Parameters
    ----------
    n_scales
        Number of log-spaced window sizes.
    min_quality
        Minimum R² for valid estimate (raises ValueError if below).
    """

    def __init__(
        self,
        n_scales: int = 20,
        min_quality: float = 0.95,
    ) -> None:
        self.n_scales = n_scales
        self.min_quality = min_quality

    def compute(self, data: np.ndarray) -> DFAEstimate:
        """Compute γ via DFA. DERIVED from H, never assigned."""
        t0 = time.perf_counter()
        x = np.asarray(data, dtype=np.float64).ravel()
        n = x.size

        if n < 128 or not np.all(np.isfinite(x)):
            elapsed = (time.perf_counter() - t0) * 1000.0
            return _invalid_estimate(n, elapsed)

        s_min = max(4, n // 50)
        s_max = n // 4
        if s_max <= s_min:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return _invalid_estimate(n, elapsed)

        scales = np.unique(np.logspace(np.log10(s_min), np.log10(s_max), self.n_scales).astype(int))
        scales = scales[scales >= 4]

        H, r_sq, fluct, valid_scales = _dfa_fit(x, scales)
        elapsed = (time.perf_counter() - t0) * 1000.0

        if not math.isfinite(H) or len(fluct) < 4:
            return _invalid_estimate(n, elapsed)

        # Wavelet cross-validation (db4)
        wavelet_confirmed = _wavelet_check(x, H)

        if r_sq < self.min_quality:
            raise ValueError(
                f"DFA r_squared={r_sq:.4f} < {self.min_quality}. "
                "Unreliable scaling fit — increase data length or check stationarity."
            )

        return DFAEstimate(
            hurst_exponent=round(H, 6),
            gamma=round(2.0 * round(H, 6) + 1.0, 6),
            dfa_fluctuations=tuple(float(f) for f in fluct),
            scale_range=(int(valid_scales[0]), int(valid_scales[-1])),
            r_squared=round(r_sq, 6),
            wavelet_confirmed=wavelet_confirmed,
            n_samples=n,
            computation_time_ms=round(elapsed, 3),
        )


def _dfa_fit(x: np.ndarray, scales: np.ndarray) -> tuple[float, float, list[float], list[int]]:
    """Core DFA: returns (H, R², fluctuations, valid_scales)."""
    y = np.cumsum(x - np.mean(x))
    n = len(y)
    fluct: list[float] = []
    valid: list[int] = []

    for s in scales:
        s_int = int(s)
        n_seg = n // s_int
        if n_seg < 1:
            continue
        var_sum = 0.0
        for v in range(n_seg):
            seg = y[v * s_int : (v + 1) * s_int]
            t = np.arange(s_int, dtype=np.float64)
            coeffs = np.polyfit(t, seg, 1)
            trend = coeffs[0] * t + coeffs[1]
            var_sum += float(np.mean((seg - trend) ** 2))
        f_s = np.sqrt(var_sum / n_seg)
        if f_s > 0 and math.isfinite(f_s):
            fluct.append(float(f_s))
            valid.append(s_int)

    if len(fluct) < 4:
        return 0.0, 0.0, [], []

    log_s = np.log(np.array(valid, dtype=np.float64))
    log_f = np.log(np.array(fluct, dtype=np.float64))

    coeffs = np.polyfit(log_s, log_f, 1)
    H = float(coeffs[0])

    pred = coeffs[0] * log_s + coeffs[1]
    ss_res = float(np.sum((log_f - pred) ** 2))
    ss_tot = float(np.sum((log_f - np.mean(log_f)) ** 2))
    r_sq = 1.0 - ss_res / (ss_tot + 1e-12)

    return H, max(0.0, r_sq), fluct, valid


def _wavelet_check(x: np.ndarray, dfa_H: float, tol: float = 0.15) -> bool:
    """Wavelet-based H estimate (db4) for cross-validation.

    H_wavelet derived from variance scaling of detail coefficients:
      Var(d_j) ∝ 2^{j(2H+1)} → H = (slope - 1) / 2
    """
    try:
        import pywt
    except ImportError:
        return False

    coeffs = pywt.wavedec(x, "db4", level=min(8, int(np.log2(len(x))) - 2))
    if len(coeffs) < 4:
        return False

    detail_vars: list[float] = []
    levels: list[float] = []
    for j, d in enumerate(coeffs[1:], start=1):
        v = float(np.var(d))
        if v > 0:
            detail_vars.append(np.log2(v))
            levels.append(float(j))

    if len(detail_vars) < 3:
        return False

    lv = np.array(levels)
    ld = np.array(detail_vars)
    slope = float(np.polyfit(lv, ld, 1)[0])
    H_wavelet = (slope - 1.0) / 2.0

    return abs(H_wavelet - dfa_H) < tol


# ──────────────────── Adaptive-criticality membrane isolation ────────────────
# INV-AC1-rev (CLAUDE.md): κ(node) ≥ κ_critical OR node ISOLATED.
#
#   κ_critical = -ln(ΔH_max / ε) / (λ_local + δ)
#
# This is the EXECUTED form of the gate that used to live only as a documented
# derivation in CLAUDE.md (and as a test-local reference implementation). The
# closed form is reproduced here verbatim — the bound is mathematically
# identical to the contract; only its home moved from prose to source.
#
#   λ_local = DFAGammaEstimator.hurst_exponent (per node, DERIVED)
#   ε       = SNR tolerance (default 0.05, env-overridable: KAPPA_EPSILON)
#   δ       = singularity floor 1e-4 (keeps λ_local→0 finite)
#   ΔH_max  = rolling max |ΔH| over the last `window` steps (window=256)
#
# Gate (the only decision): isolate(node) ⇔ κ_node < κ_critical(λ_local).
#
# NON-CLAIM: a criticality observer, not a predictor. It classifies the scaling
# topology of a node; it makes no market-causality / forecasting claim.
KAPPA_DELTA: float = 1e-4  # δ : singularity floor (INV-AC1-rev)
KAPPA_EPSILON_DEFAULT: float = 0.05  # ε : SNR tolerance
KAPPA_WINDOW_DEFAULT: int = 256  # rolling window for ΔH_max
KAPPA_EPSILON_ENV: str = "KAPPA_EPSILON"
KAPPA_WINDOW_ENV: str = "KAPPA_WINDOW"


class IsolationReason(str, Enum):
    """Why a node was (not) isolated — deterministic, audit-friendly enum."""

    NONE = "NONE"
    BELOW_KAPPA_CRITICAL = "BELOW_KAPPA_CRITICAL"
    NON_FINITE_INPUT = "NON_FINITE_INPUT"
    SINGULAR_DENOMINATOR = "SINGULAR_DENOMINATOR"


@dataclass(frozen=True, slots=True)
class CriticalityAssessment:
    """Per-node adaptive-criticality verdict (INV-AC1-rev).

    Every field that feeds the gate decision is exposed so the verdict is
    fully reconstructable from the record (no hidden state).
    """

    lambda_local: float
    delta_h_max: float
    epsilon: float
    kappa_critical: float
    kappa_node: float
    isolation_required: bool
    isolation_reason: IsolationReason


def resolve_kappa_epsilon(epsilon: float | None = None) -> float:
    """ε with deterministic env override (KAPPA_EPSILON). Fail-closed on bad ε."""
    if epsilon is not None:
        eps = float(epsilon)
    else:
        raw = os.environ.get(KAPPA_EPSILON_ENV)
        eps = KAPPA_EPSILON_DEFAULT if raw is None else float(raw)
    if not math.isfinite(eps) or eps <= 0.0:
        raise ValueError(f"INV-AC1-rev: ε must be finite > 0, got {eps!r}")
    return eps


def resolve_kappa_window(window: int | None = None) -> int:
    """Rolling window with deterministic env override (KAPPA_WINDOW)."""
    if window is not None:
        w = int(window)
    else:
        raw = os.environ.get(KAPPA_WINDOW_ENV)
        w = KAPPA_WINDOW_DEFAULT if raw is None else int(raw)
    if w < 2:
        raise ValueError(f"INV-AC1-rev: window must be >= 2, got {w}")
    return w


def kappa_critical(lambda_local: float, *, eps: float, dh_max: float) -> float:
    """κ_critical = -ln(ΔH_max/ε)/(λ_local + δ) — INV-AC1-rev closed form.

    Fail-closed: a structural contract violation (non-finite / non-positive ε
    or ΔH_max, non-finite λ_local, singular denominator) raises ``ValueError``
    rather than returning a silent fallback. The bound is mathematically
    identical to the CLAUDE.md derivation block.
    """
    if not math.isfinite(eps) or eps <= 0.0:
        raise ValueError(f"INV-AC1-rev: ε must be finite > 0, got {eps!r}")
    if not math.isfinite(dh_max) or dh_max <= 0.0:
        raise ValueError(f"INV-AC1-rev: ΔH_max must be finite > 0, got {dh_max!r}")
    if not math.isfinite(lambda_local):
        raise ValueError(f"INV-AC1-rev: λ_local must be finite, got {lambda_local!r}")
    denom = lambda_local + KAPPA_DELTA
    if denom <= 0.0:
        raise ValueError(f"INV-AC1-rev: singular denominator λ_local+δ={denom!r} ≤ 0")
    return -math.log(dh_max / eps) / denom


def should_isolate_node(
    kappa_node: float, lambda_local: float, *, eps: float, dh_max: float
) -> bool:
    """Gate: isolate iff κ_node < κ_critical(λ_local).

    Fail-closed on a non-finite κ_node: a node whose curvature cannot be placed
    relative to the threshold is excluded (True), never silently admitted.
    """
    if not math.isfinite(kappa_node):
        return True
    return kappa_node < kappa_critical(lambda_local, eps=eps, dh_max=dh_max)


def assess_node(
    kappa_node: float,
    lambda_local: float,
    dh_max: float,
    *,
    epsilon: float | None = None,
) -> CriticalityAssessment:
    """Full INV-AC1-rev verdict for one node, with the reason recorded.

    Runtime-robust fail-closed semantics: a non-finite κ_node/λ_local or a
    singular denominator isolates that single node (NON_FINITE_INPUT /
    SINGULAR_DENOMINATOR) instead of crashing the whole ensemble. The shared
    ensemble parameters ε and ΔH_max are validated up front and raise on
    violation (a wrong ε/ΔH_max is a programming error, not node data).
    """
    eps = resolve_kappa_epsilon(epsilon)
    if not math.isfinite(dh_max) or dh_max <= 0.0:
        raise ValueError(f"INV-AC1-rev: ΔH_max must be finite > 0, got {dh_max!r}")

    if not math.isfinite(kappa_node) or not math.isfinite(lambda_local):
        return CriticalityAssessment(
            lambda_local=lambda_local,
            delta_h_max=dh_max,
            epsilon=eps,
            kappa_critical=math.nan,
            kappa_node=kappa_node,
            isolation_required=True,
            isolation_reason=IsolationReason.NON_FINITE_INPUT,
        )

    denom = lambda_local + KAPPA_DELTA
    if denom <= 0.0:
        return CriticalityAssessment(
            lambda_local=lambda_local,
            delta_h_max=dh_max,
            epsilon=eps,
            kappa_critical=math.nan,
            kappa_node=kappa_node,
            isolation_required=True,
            isolation_reason=IsolationReason.SINGULAR_DENOMINATOR,
        )

    k_crit = -math.log(dh_max / eps) / denom
    isolate = kappa_node < k_crit
    return CriticalityAssessment(
        lambda_local=lambda_local,
        delta_h_max=dh_max,
        epsilon=eps,
        kappa_critical=k_crit,
        kappa_node=kappa_node,
        isolation_required=isolate,
        isolation_reason=(
            IsolationReason.BELOW_KAPPA_CRITICAL if isolate else IsolationReason.NONE
        ),
    )


def isolation_mask(
    kappa_nodes: NDArray[np.float64] | list[float],
    lambda_locals: NDArray[np.float64] | list[float],
    dh_max: float,
    *,
    epsilon: float | None = None,
) -> NDArray[np.bool_]:
    """Deterministic per-node exclusion mask (True = isolated).

    No node registry exists in this layer, so isolation is expressed as a
    boolean mask the ensemble aggregator applies — not as mutation of a graph.
    """
    k = np.asarray(kappa_nodes, dtype=np.float64).ravel()
    lam = np.asarray(lambda_locals, dtype=np.float64).ravel()
    if k.shape != lam.shape:
        raise ValueError(
            f"kappa_nodes {k.shape} and lambda_locals {lam.shape} must align (INV-AC1-rev)."
        )
    return np.array(
        [
            assess_node(float(kn), float(ln), dh_max, epsilon=epsilon).isolation_required
            for kn, ln in zip(k, lam, strict=True)
        ],
        dtype=np.bool_,
    )


def aggregate_excluding_isolated(
    values: NDArray[np.float64] | list[float],
    kappa_nodes: NDArray[np.float64] | list[float],
    lambda_locals: NDArray[np.float64] | list[float],
    dh_max: float,
    *,
    epsilon: float | None = None,
) -> float:
    """Mean of ``values`` over the non-isolated nodes (INV-AC1-rev exclusion).

    Fail-closed: if every node is isolated there is no admissible ensemble and
    a ``ValueError`` is raised rather than returning a fabricated aggregate.
    """
    vals = np.asarray(values, dtype=np.float64).ravel()
    iso = isolation_mask(kappa_nodes, lambda_locals, dh_max, epsilon=epsilon)
    if vals.shape != iso.shape:
        raise ValueError(f"values {vals.shape} and node count {iso.shape} must align.")
    keep = ~iso
    if not bool(keep.any()):
        raise ValueError(
            "INV-AC1-rev: all nodes isolated — fail-closed, no admissible ensemble aggregate."
        )
    return float(np.mean(vals[keep]))


class AdaptiveCriticalityGate:
    """Executed INV-AC1-rev membrane-isolation gate over a DFA λ_local field.

    Thin, deterministic wrapper binding a fixed ε to the module-level gate
    functions. There is no node registry at this layer, so ``isolation_mask``
    (a deterministic boolean exclusion mask) is the runtime isolation form —
    there is no ``isolate_node`` mutation to apply.
    """

    def __init__(self, *, epsilon: float | None = None) -> None:
        self.epsilon: float = resolve_kappa_epsilon(epsilon)

    def kappa_critical(self, lambda_local: float, dh_max: float) -> float:
        return kappa_critical(lambda_local, eps=self.epsilon, dh_max=dh_max)

    def assess_node(
        self, kappa_node: float, lambda_local: float, dh_max: float
    ) -> CriticalityAssessment:
        return assess_node(kappa_node, lambda_local, dh_max, epsilon=self.epsilon)

    def should_isolate_node(self, kappa_node: float, lambda_local: float, dh_max: float) -> bool:
        return should_isolate_node(kappa_node, lambda_local, eps=self.epsilon, dh_max=dh_max)

    def isolation_mask(
        self,
        kappa_nodes: NDArray[np.float64] | list[float],
        lambda_locals: NDArray[np.float64] | list[float],
        dh_max: float,
    ) -> NDArray[np.bool_]:
        return isolation_mask(kappa_nodes, lambda_locals, dh_max, epsilon=self.epsilon)

    def aggregate_excluding_isolated(
        self,
        values: NDArray[np.float64] | list[float],
        kappa_nodes: NDArray[np.float64] | list[float],
        lambda_locals: NDArray[np.float64] | list[float],
        dh_max: float,
    ) -> float:
        return aggregate_excluding_isolated(
            values, kappa_nodes, lambda_locals, dh_max, epsilon=self.epsilon
        )
