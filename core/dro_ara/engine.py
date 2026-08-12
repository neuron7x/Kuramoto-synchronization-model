# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""DRO-ARA v7 — Deterministic Recursive Observer + Action Result Acceptor.

Measures statistical regime of a price series via Hurst (H) on log-returns (DFA-1),
confirms stationarity via lag-augmented ADF on log-returns (AIC lag selection,
Ng & Perron 2001), and emits a deterministic regime + trading signal through a
bounded ARA feedback loop. Both statistical tests operate on the same transform
(∆ log price) — the convention was aligned in PR #345 (RFC-stationarity).

Public invariants (never relaxed):

* ``gamma = 2*H + 1``   — derived from H, never assigned independently.
* ``rs = max(0, 1 - |gamma - 1|)`` — risk scalar ∈ [0, 1].
* Regime is INVALID when ADF rejects stationarity OR DFA R² < 0.90.
* Signal LONG requires CRITICAL regime AND rs > 0.33 AND trend ∈ {CONVERGING,
  STABLE}.
* Degenerate input (NaN/Inf, constant, wrong rank, too short) raises
  ``ValueError`` — fail-closed, never silent.

References:
    Dickey & Fuller (1979); Ng & Perron (2001); Peng et al. (1994, DFA);
    MacKinnon (1994, ADF critical values).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Iterator, NamedTuple

import numpy as np
from numpy.typing import NDArray

from geosync_hpc.control.action_result_comparator import (
    ExpectedResultModel,
    ObservedActionResult,
    accept_action_result,
)

__all__ = [
    "Regime",
    "Signal",
    "State",
    "derive_gamma",
    "risk_scalar",
    "classify",
    "geosync_observe",
    "MAX_DEPTH",
    "MIN_WINDOW",
    "R2_MIN",
    "EPSILON_H",
    "STABLE_RUNS",
    "H_CRITICAL",
    "H_DRIFT",
    "ADF_CV_5PCT",
    "ADF_MAX_LAGS",
    "RS_LONG_THRESH",
    "FREE_ENERGY_CRITICAL",
    "VARIATIONAL_ENERGY_FLOOR",
    "VARIATIONAL_ENERGY_CEILING",
]

MAX_DEPTH: Final[int] = 32
MIN_WINDOW: Final[int] = 64
MIN_BOXES: Final[int] = 4
R2_MIN: Final[float] = 0.90
EPSILON_H: Final[float] = 0.02
STABLE_RUNS: Final[int] = 3
H_CRITICAL: Final[float] = 0.45
H_DRIFT: Final[float] = 0.55
ADF_CV_5PCT: Final[float] = -2.86
ADF_MAX_LAGS: Final[int] = 4
RS_LONG_THRESH: Final[float] = 0.33
FREE_ENERGY_CRITICAL: Final[float] = 0.25
VARIATIONAL_ENERGY_FLOOR: Final[float] = 0.05
VARIATIONAL_ENERGY_CEILING: Final[float] = 2.0


class Regime(str, Enum):
    CRITICAL = "CRITICAL"
    TRANSITION = "TRANSITION"
    DRIFT = "DRIFT"
    INVALID = "INVALID"


class Signal(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"
    REDUCE = "REDUCE"


def _adf_stationary(x: NDArray[np.float64]) -> bool:
    """Lag-augmented ADF test with AIC lag selection.

    Model: Δxₜ = β·xₜ₋₁ + Σ γₖ·Δxₜ₋ₖ + εₜ. H₀: β = 0 (unit root). Reject H₀ when
    t_β < ADF_CV_5PCT → series declared stationary. Returns True when rejected.
    """
    if len(x) < 20:
        return True
    dy = np.diff(x)
    best_aic = np.inf
    best_t = 0.0

    for k in range(0, ADF_MAX_LAGS + 1):
        min_idx = k + 1
        y_ = dy[min_idx:]
        xl_ = x[min_idx:-1] - x[min_idx:-1].mean()

        if k == 0:
            Z = xl_.reshape(-1, 1)
        else:
            lags = np.column_stack([dy[min_idx - j : -j] for j in range(1, k + 1)])
            Z = np.column_stack([xl_, lags])

        ZtZ = Z.T @ Z + np.eye(Z.shape[1]) * 1e-10
        coef = np.linalg.solve(ZtZ, Z.T @ y_)
        res = y_ - Z @ coef
        s2 = float(np.sum(res**2) / max(len(res) - Z.shape[1], 1))

        aic = len(y_) * np.log(s2 + 1e-12) + 2 * Z.shape[1]
        if aic < best_aic:
            best_aic = aic
            se_beta = float(np.sqrt(s2 * np.linalg.inv(ZtZ)[0, 0]))
            best_t = float(coef[0] / (se_beta + 1e-12))

    return bool(best_t < ADF_CV_5PCT)


def _validate(x: NDArray[np.float64] | np.ndarray, min_len: int) -> NDArray[np.float64]:
    arr: NDArray[np.float64] = np.asarray(x, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"1-D required, got {arr.shape}")
    if len(arr) < min_len:
        raise ValueError(f"need ≥{min_len}, got {len(arr)}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("NaN/Inf in input")
    if np.all(arr == arr[0]):
        raise ValueError("constant series")
    return arr


def _hurst_dfa(x: NDArray[np.float64]) -> tuple[float, float]:
    """DFA-1 on log-returns. Returns (H, R²).

    Log-returns are detrended by construction (linear drift in prices → constant
    in log-returns → zero-mean after demeaning), so the H estimate is unbiased
    across drift magnitudes.
    """
    r = np.diff(np.log(np.abs(x) + 1e-12))
    y = np.cumsum(r - r.mean())
    N = len(y)
    min_box = max(8, N // 64)
    max_box = N // MIN_BOXES
    if max_box < min_box:
        return 0.5, 0.0
    sizes = np.unique(np.round(np.geomspace(min_box, max_box, 16)).astype(int))
    sizes = sizes[(sizes >= min_box) & (sizes <= max_box)]
    if len(sizes) < 3:
        return 0.5, 0.0

    Fv_list: list[float] = []
    sv_list: list[int] = []
    for n in sizes:
        nb = N // n
        if nb < MIN_BOXES:
            continue
        seg = y[: nb * n].reshape(nb, n)
        t_ = np.arange(n, dtype=float)
        t_ -= t_.mean()
        s_ = seg - seg.mean(axis=1, keepdims=True)
        sl = (s_ @ t_) / (t_ @ t_)
        res = s_ - sl[:, None] * t_[None, :]
        Fn = float(np.sqrt(np.mean(res**2)))
        if Fn > 0 and np.isfinite(Fn):
            Fv_list.append(Fn)
            sv_list.append(int(n))

    if len(Fv_list) < 3:
        return 0.5, 0.0
    Fv = np.asarray(Fv_list, dtype=np.float64)
    if not np.all(Fv > 0):
        return 0.5, 0.0

    ln = np.log(np.asarray(sv_list, dtype=np.float64))
    lF = np.log(Fv)
    H_raw, b = np.polyfit(ln, lF, 1)
    ss_res = float(np.sum((lF - (H_raw * ln + b)) ** 2))
    ss_tot = float(np.sum((lF - lF.mean()) ** 2))
    # bounds: R2 is a coefficient of determination; contract keeps it in [0, 1].
    r2 = float(np.clip(1 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0, 0.0, 1.0))
    # bounds: finite-sample DFA H is exported only inside the open unit interval.
    return float(np.clip(H_raw, 0.01, 0.99)), r2


def derive_gamma(x: NDArray[np.float64] | np.ndarray) -> tuple[float, float, float]:
    """Return (gamma, H, r2) with invariant gamma = 2·H + 1.

    Enforces INV-DRO5 (fail-closed): ``ValueError`` is raised on
    NaN, ±Inf, constant series, non-1-D, or shorter-than-64-sample
    inputs — no silent numeric repair. The 64-sample floor matches
    the DFA inner-loop requirement (``min_box = max(8, N // 64)``);
    legitimate production windows (default 512) are well above it.
    """
    arr = _validate(x, min_len=64)
    H, r2 = _hurst_dfa(arr)
    return round(2 * H + 1, 6), round(H, 6), round(r2, 6)


def risk_scalar(gamma: float) -> float:
    return round(max(0.0, 1.0 - abs(gamma - 1.0)), 6)


def classify(gamma: float, r2: float, stationary: bool) -> Regime:
    if not stationary or r2 < R2_MIN:
        return Regime.INVALID
    H = (gamma - 1.0) / 2.0
    if H < H_CRITICAL:
        return Regime.CRITICAL
    if H < H_DRIFT:
        return Regime.TRANSITION
    return Regime.DRIFT


@dataclass(frozen=True)
class State:
    gamma: float
    H: float
    r2: float
    regime: Regime
    rs: float
    stationary: bool

    @classmethod
    def from_window(cls, x: NDArray[np.float64] | np.ndarray) -> "State":
        arr: NDArray[np.float64] = np.asarray(x, dtype=np.float64)
        # INV-DRO3 convention fix (PR #345 RFC): ADF runs on log-returns, not
        # raw prices. Aligns with DFA input (engine.py:138) — was a
        # near-tautology on I(1) asset prices when tested on levels.
        log_returns = np.diff(np.log(np.abs(arr) + 1e-12))
        stat = _adf_stationary(log_returns)
        g, H, r2 = derive_gamma(arr)
        reg = classify(g, r2, stat)
        rs = risk_scalar(g) if reg != Regime.INVALID else 0.0
        return cls(gamma=g, H=H, r2=r2, regime=reg, rs=rs, stationary=stat)


def _windows(p: NDArray[np.float64], w: int, s: int) -> Iterator[NDArray[np.float64]]:
    for i in range(0, len(p) - w, s):
        yield p[i : i + w]


class _CausalChronology:
    """Monotone hash-chain allocator for DRO-ARA internal events.

    The public ``geosync_observe`` API is still deterministic for replay, but
    sequence numbers are now allocated from observed event transitions and bound
    into a SHA-256 chain instead of being derived from a loop-index formula.
    """

    def __init__(self) -> None:
        self._next_seq = 1
        self.chain_hash = "0" * 64

    def bind(self, phase: str, payload: dict[str, float | int | str]) -> int:
        seq = self._next_seq
        self._next_seq += 1
        body = {"parent": self.chain_hash, "phase": phase, "seq": seq, "payload": payload}
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.chain_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return seq


class _ARA(NamedTuple):
    pred: float
    regime: Regime
    errors: tuple[float, ...]
    variational_energy: tuple[float, ...]
    stable: int
    belief_mean: float
    belief_variance: float
    adaptive_threshold: float


def _adaptive_energy_threshold(actual: State) -> float:
    """Context-conditioned free-energy gate derived from the current state."""

    phase_transition_pressure = 1.0 + abs(actual.H - 0.5)
    evidence_quality = 0.5 + actual.r2
    risk_capacity = 0.5 + actual.rs
    threshold = FREE_ENERGY_CRITICAL * evidence_quality * risk_capacity / phase_transition_pressure
    # bounds: adaptive energy gate is limited by the exported floor/ceiling contract.
    return round(float(np.clip(threshold, VARIATIONAL_ENERGY_FLOOR, VARIATIONAL_ENERGY_CEILING)), 6)


def _variational_energy(error: float, belief_mean: float, belief_variance: float, predicted: float) -> float:
    """Gaussian variational surrogate: accuracy surprise + complexity penalty."""

    variance = max(belief_variance, 1e-9)
    surprise = 0.5 * (math.log(2.0 * math.pi * variance) + (error * error) / variance)
    complexity = 0.5 * ((predicted - belief_mean) ** 2) / variance
    return round(max(0.0, float(surprise + complexity)), 6)


def _update_belief_variance(previous: float, error: float, actual: State) -> float:
    context_floor = max(EPSILON_H * EPSILON_H, (1.0 - actual.r2 + 1e-6) * 0.05)
    updated = 0.85 * previous + 0.15 * max(error * error, context_floor)
    # bounds: belief variance is kept finite for Gaussian surrogate stability.
    return round(float(np.clip(updated, 1e-6, 4.0)), 6)


def _ara_comparator_error(predicted_gamma: float, actual: State, chronology: _CausalChronology) -> float:
    """Return deterministic ActionResultComparator error for one DRO-ARA event."""

    model_seq = chronology.bind(
        "MODEL_SEALED",
        {"predicted_gamma": round(predicted_gamma, 6), "H": actual.H, "r2": actual.r2, "rs": actual.rs},
    )
    action_seq = chronology.bind("ACTION_DISPATCHED", {"predicted_gamma": round(predicted_gamma, 6)})
    observed_seq = chronology.bind("AFFERENTATION_RECEIVED", {"actual_gamma": actual.gamma})
    expected = ExpectedResultModel(
        action_id=f"dro-ara:{model_seq}:{action_seq}:{observed_seq}",
        action_type="regime_observe",
        expected_result=(predicted_gamma,),
        expected_result_variance=(1.0,),
        context_signature=(actual.H, actual.r2, actual.rs),
        model_created_seq=model_seq,
        action_started_seq=action_seq,
        error_threshold=EPSILON_H,
        rollback_threshold=max(EPSILON_H * 10.0, 1.0),
    )
    observed = ObservedActionResult(
        action_id=expected.action_id,
        observed_seq=observed_seq,
        observed_result=(actual.gamma,),
        reverse_afferentation_present=True,
    )
    witness = accept_action_result(expected, observed)
    if witness.comparator_error is None:
        raise ValueError(f"DRO-ARA comparator failed closed: {witness.reason}")
    return witness.comparator_error


def _ara_step(a: _ARA, actual: State, alpha: float, chronology: _CausalChronology) -> _ARA:
    """Advance one bounded ARA step with comparator-backed chronology."""

    err = _ara_comparator_error(a.pred, actual, chronology)
    err_rounded = round(float(err), 6)
    adaptive_threshold = _adaptive_energy_threshold(actual)
    energy = _variational_energy(err_rounded, a.belief_mean, a.belief_variance, a.pred)
    next_errors = (a.errors + (err_rounded,))[-STABLE_RUNS:]
    next_energy = (a.variational_energy + (energy,))[-STABLE_RUNS:]
    stable = a.stable + 1 if err_rounded < EPSILON_H and energy <= adaptive_threshold else 0
    pred = round(float(a.pred + alpha * (actual.gamma - a.pred)), 6)
    belief_mean = round(float(a.belief_mean + alpha * (actual.gamma - a.belief_mean)), 6)
    belief_variance = _update_belief_variance(a.belief_variance, err_rounded, actual)
    return _ARA(
        pred=pred,
        regime=actual.regime,
        errors=next_errors,
        variational_energy=next_energy,
        stable=stable,
        belief_mean=belief_mean,
        belief_variance=belief_variance,
        adaptive_threshold=adaptive_threshold,
    )


def _converged(a: _ARA) -> bool:
    return a.stable >= STABLE_RUNS


def _free_energy(a: _ARA) -> float:
    if not a.variational_energy:
        return 0.0
    return round(float(np.mean(a.variational_energy[-STABLE_RUNS:])), 6)


def _trend(a: _ARA) -> str | None:
    signal = a.variational_energy if len(a.variational_energy) >= 2 else a.errors
    if len(signal) < 2:
        return None
    w = signal[-4:]
    if w[-1] < w[0] * 0.7:
        return "CONVERGING"
    if w[-1] > w[0] * 1.3:
        return "DIVERGING"
    return "STABLE"


def _dro(price: NDArray[np.float64], window: int, step: int, alpha: float) -> tuple[State, _ARA, str]:
    gen = _windows(price, window, step)
    chronology = _CausalChronology()
    s = State.from_window(next(gen))
    initial_variance = max(EPSILON_H * EPSILON_H, 1.0 - s.r2 + 1e-6)
    ara = _ARA(s.gamma, s.regime, (), (), 0, s.gamma, round(initial_variance, 6), _adaptive_energy_threshold(s))
    for depth, w in enumerate(gen):
        if depth >= MAX_DEPTH:
            break
        s = State.from_window(w)
        ara = _ara_step(ara, s, alpha, chronology)
        if _converged(ara):
            break
    return s, ara, chronology.chain_hash


def _recovery_action(free_energy: float, threshold: float, belief_variance: float) -> str:
    """Return the bounded generative-recovery action for the current belief state."""

    if free_energy > threshold:
        return "REDUCE_RISK"
    if free_energy > threshold * 0.5 or belief_variance > threshold:
        return "EXPAND_CONTEXT"
    return "ALLOW_MODEL_UPDATE"


def geosync_observe(
    price: NDArray[np.float64] | np.ndarray,
    window: int = 512,
    step: int = 64,
) -> dict[str, Any]:
    """Public API: observe a price series and emit a regime + signal verdict.

    :param price: 1-D finite non-constant price array with length ≥ window+step.
    :param window: DFA window size; ≥ 512 recommended so DFA spans ≥ 3 octaves
        and R² typically > 0.90.
    :param step: stride between DRO iterations; EMA α = 2/(N+1) where
        N = (len(price) − window) // step.

    Invariants enforced on return:

    * ``gamma`` == 2·``H`` + 1 (rounded)
    * ``risk_scalar`` ∈ [0, 1]
    * ``regime`` ∈ {CRITICAL, TRANSITION, DRIFT, INVALID}
    * ``signal`` ∈ {LONG, SHORT, HOLD, REDUCE}
    """
    arr = _validate(price, min_len=window + step)
    N = (len(arr) - window) // step
    alpha = 2.0 / (N + 1)
    s, ara, chronology_hash = _dro(arr, window, step, alpha)
    trend = _trend(ara)
    free_energy = _free_energy(ara)
    dynamic_free_energy_threshold = ara.adaptive_threshold
    circuit_breaker = free_energy > dynamic_free_energy_threshold

    if circuit_breaker:
        regime = Regime.INVALID
        risk_scalar_value = 0.0
        signal = Signal.REDUCE
        converged = False
    else:
        regime = s.regime
        risk_scalar_value = s.rs
        converged = _converged(ara)
        if s.regime == Regime.CRITICAL and s.rs > RS_LONG_THRESH and trend in ("CONVERGING", "STABLE"):
            signal = Signal.LONG
        elif s.regime == Regime.DRIFT and trend == "DIVERGING":
            signal = Signal.SHORT
        elif trend in ("CONVERGING", "STABLE"):
            signal = Signal.HOLD
        else:
            signal = Signal.REDUCE

    return {
        "gamma": s.gamma,
        "H": s.H,
        "r2_dfa": s.r2,
        "regime": regime.value,
        "risk_scalar": risk_scalar_value,
        "stationary": s.stationary,
        "signal": signal.value,
        "free_energy": free_energy,
        "free_energy_circuit_breaker": circuit_breaker,
        "dynamic_free_energy_threshold": dynamic_free_energy_threshold,
        "belief_mean": ara.belief_mean,
        "belief_variance": ara.belief_variance,
        "causal_chronology_hash": chronology_hash,
        "recovery_action": _recovery_action(free_energy, dynamic_free_energy_threshold, ara.belief_variance),
        "ara_steps": len(ara.errors),
        "converged": converged,
        "trend": trend,
        "alpha_ema": round(alpha, 6),
    }
