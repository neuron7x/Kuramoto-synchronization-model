# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

# Iteration cap for the asymmetric-least-squares IRLS below. The expectile problem
# is strictly convex, so a well-posed input converges far inside this bound; the
# cap exists only to turn a numerical pathology into a raised error, never a
# silently-returned non-converged iterate.
_IRLS_MAX_ITER = 256


def _finite(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _finite_array(name: str, values: FloatArray) -> FloatArray:
    if not bool(np.all(np.isfinite(values))):
        raise ValueError(f"{name} must be finite")
    return values


def expectile_of_samples(samples: npt.ArrayLike, tau: float) -> float:
    tau = _finite("tau", float(tau))
    if not 0.0 < tau < 1.0:
        raise ValueError("tau must be in (0, 1)")
    arr = cast(FloatArray, np.asarray(samples, dtype=np.float64).ravel())
    if arr.size == 0:
        raise ValueError("samples must be non-empty")
    _finite_array("samples", arr)
    scale = max(1.0, _finite("sample scale", float(np.max(np.abs(arr)))))  # bounds: scale ≥ 1
    scaled = cast(FloatArray, arr / scale)
    estimate = _finite("expectile seed", float(np.median(scaled)))
    # Asymmetric-least-squares IRLS. The expectile problem is strictly convex, so
    # this iteration is globally convergent; exhausting the cap without meeting the
    # tolerance signals a numerical pathology, not a valid answer. Refuse to return
    # a non-converged iterate (INV: flag/fail, never fabricate) rather than silently
    # emit the last step as if it were the fixed point.
    max_iter = _IRLS_MAX_ITER
    converged = False
    for _ in range(max_iter):
        upper = scaled >= estimate
        denom = tau * float(np.count_nonzero(upper))
        denom += (1.0 - tau) * float(np.count_nonzero(~upper))
        if denom <= 0.0:
            # Unreachable for tau ∈ (0,1) and a non-empty sample (every point falls
            # in exactly one side, both weights > 0). Guard defensively: a zero
            # denominator would be a broken invariant, so fail closed.
            raise ValueError("expectile IRLS reached a degenerate zero denominator")
        residual = tau * float(np.sum(scaled[upper] - estimate))
        residual += (1.0 - tau) * float(np.sum(scaled[~upper] - estimate))
        next_estimate = _finite("scaled expectile", estimate + residual / denom)
        if abs(next_estimate - estimate) <= 1e-13 * (1.0 + abs(estimate)):
            estimate = next_estimate
            converged = True
            break
        estimate = next_estimate
    if not converged:
        raise ValueError(
            f"expectile IRLS did not converge in {max_iter} iterations (tau={tau}); "
            "refusing to fabricate a non-convergent estimate"
        )
    return _finite("expectile", float(estimate * scale))


@dataclass(frozen=True)
class ExpectileChannel:
    tau: float
    learning_rate: float

    def __post_init__(self) -> None:
        tau = _finite("tau", float(self.tau))
        rate = _finite("learning_rate", float(self.learning_rate))
        if not 0.0 < tau < 1.0:
            raise ValueError("tau must be in (0, 1)")
        if not 0.0 < rate <= 1.0:
            raise ValueError("learning_rate must be in (0, 1]")
        object.__setattr__(self, "tau", tau)
        object.__setattr__(self, "learning_rate", rate)

    @property
    def alpha_pos(self) -> float:
        return self.learning_rate * self.tau

    @property
    def alpha_neg(self) -> float:
        return self.learning_rate * (1.0 - self.tau)

    def recovered_tau(self) -> float:
        total = _finite("alpha_total", self.alpha_pos + self.alpha_neg)
        return _finite("recovered_tau", self.alpha_pos / total)


class ExpectileEnsembleValue:
    _taus: FloatArray
    _alpha_pos: FloatArray
    _alpha_neg: FloatArray
    _values: FloatArray
    _n_updates: int

    def __init__(
        self,
        channels: list[ExpectileChannel],
        *,
        init_value: float = 0.0,
    ) -> None:
        if not channels:
            raise ValueError("ensemble requires at least one channel")
        init_value = _finite("init_value", float(init_value))
        ordered = tuple(sorted(channels, key=lambda item: item.tau))
        if len({item.tau for item in ordered}) != len(ordered):
            raise ValueError("channel tau levels must be unique")
        self._taus = cast(
            FloatArray,
            np.array([item.tau for item in ordered], dtype=np.float64),
        )
        self._alpha_pos = cast(
            FloatArray,
            np.array([item.alpha_pos for item in ordered], dtype=np.float64),
        )
        self._alpha_neg = cast(
            FloatArray,
            np.array([item.alpha_neg for item in ordered], dtype=np.float64),
        )
        self._values = cast(
            FloatArray,
            np.full(len(ordered), init_value, dtype=np.float64),
        )
        _finite_array("initial values", self._values)
        self._n_updates = 0

    @classmethod
    def symmetric(
        cls,
        *,
        n_channels: int = 1,
        learning_rate: float = 0.05,
    ) -> ExpectileEnsembleValue:
        if n_channels != 1:
            raise ValueError("symmetric ensemble is the single tau=0.5 channel")
        return cls([ExpectileChannel(0.5, learning_rate)])

    @classmethod
    def from_levels(
        cls,
        taus: npt.ArrayLike,
        *,
        learning_rate: float = 0.05,
        init_value: float = 0.0,
    ) -> ExpectileEnsembleValue:
        levels = cast(FloatArray, np.asarray(taus, dtype=np.float64).ravel())
        channels = [ExpectileChannel(float(level), learning_rate) for level in levels]
        return cls(channels, init_value=init_value)

    @classmethod
    def spread(
        cls,
        n_channels: int = 9,
        *,
        learning_rate: float = 0.05,
        init_value: float = 0.0,
    ) -> ExpectileEnsembleValue:
        if n_channels < 1:
            raise ValueError("n_channels must be >= 1")
        levels = np.arange(1, n_channels + 1, dtype=np.float64)
        levels = levels / (n_channels + 1)
        return cls.from_levels(
            levels,
            learning_rate=learning_rate,
            init_value=init_value,
        )

    def observe_return(self, target: float) -> FloatArray:
        target = _finite("target", float(target))
        # Overflow in the array arithmetic is a contract violation, not a runtime
        # warning to leak: raise the SAME finite-contract error deterministically,
        # under errstate, and leave state unmutated.
        with np.errstate(over="raise", invalid="raise"):
            try:
                deltas = cast(FloatArray, target - self._values)
            except FloatingPointError as exc:
                raise ValueError("distributional deltas must be finite") from exc
            deltas = _finite_array("distributional deltas", deltas)
            rates = cast(
                FloatArray,
                np.where(deltas > 0.0, self._alpha_pos, self._alpha_neg),
            )
            try:
                updated = cast(FloatArray, self._values + rates * deltas)
            except FloatingPointError as exc:
                raise ValueError("updated values must be finite") from exc
        self._values = _finite_array("updated values", updated)
        self._n_updates += 1
        return cast(FloatArray, deltas.copy())

    def observe_td_target(
        self,
        reward: float,
        next_value: float,
        discount_gamma: float,
    ) -> FloatArray:
        reward = _finite("reward", float(reward))
        next_value = _finite("next_value", float(next_value))
        gamma = _finite("discount_gamma", float(discount_gamma))
        if not 0.0 < gamma <= 1.0:
            raise ValueError("discount_gamma must be in (0, 1]")
        return self.observe_return(_finite("td_target", reward + gamma * next_value))

    @property
    def taus(self) -> FloatArray:
        return cast(FloatArray, self._taus.copy())

    @property
    def values(self) -> FloatArray:
        return cast(FloatArray, self._values.copy())

    def expectile_curve(self) -> tuple[FloatArray, FloatArray]:
        return self.taus, self.values

    def canonical_value(self) -> float:
        exact = np.isclose(self._taus, 0.5)
        if bool(np.any(exact)):
            index = int(np.flatnonzero(exact)[0])
            return _finite("canonical_value", float(self._values[index]))
        value = float(np.interp(0.5, self._taus, self._values))
        return _finite("canonical_value", value)

    def risk_adjusted_value(self, tau: float) -> float:
        tau = _finite("tau", float(tau))
        if not 0.0 < tau < 1.0:
            raise ValueError("tau must be in (0, 1)")
        value = float(np.interp(tau, self._taus, self._values))
        return _finite("risk_adjusted_value", value)

    def dispersion(self) -> float:
        return _finite("dispersion", float(self._values[-1] - self._values[0]))

    @property
    def n_updates(self) -> int:
        return self._n_updates
