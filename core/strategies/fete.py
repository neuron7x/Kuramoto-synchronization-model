# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fractal Ethical Trading Engine (FETE) integration for GeoSync."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Dict, Tuple

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.signal import detrend

EPS: float = 1e-10
EPS_PROB_CLIP: float = 1e-5
TAU_MIN: float = 0.5
TAU_MAX: float = 2.0


class Regime(str, Enum):
    """Market regime classification."""

    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    NOISE = "noise"
    CALIBRATING = "calibrating"


def binary_entropy(probabilities: ArrayLike) -> NDArray[np.float64]:
    """Compute binary entropy for probabilities with numerical stability."""

    probs = np.clip(np.asarray(probabilities, dtype=float), EPS_PROB_CLIP, 1.0 - EPS_PROB_CLIP)
    return -(probs * np.log(probs) + (1.0 - probs) * np.log(1.0 - probs))


class FractalEMA:
    """Hierarchical exponential moving average with fractal weights."""

    def __init__(
        self, shape: Tuple[int, ...] = (1,), *, levels: int = 5, base: float = 0.6
    ) -> None:
        self.levels = levels
        self.rates = [float(base) ** (k + 1) for k in range(levels)]
        self.states = [np.zeros(shape, dtype=float) for _ in range(levels)]
        weights = np.array([1.0 / (k + 1) for k in range(levels)], dtype=float)
        self.weights = weights / weights.sum()

    def update(self, values: ArrayLike) -> NDArray[np.float64]:
        """Return aggregated EMA across scales for the provided values."""

        x = np.asarray(values, dtype=float)
        aggregate = np.zeros_like(self.states[0], dtype=float)
        for idx, rate in enumerate(self.rates):
            self.states[idx] = (1.0 - rate) * self.states[idx] + rate * x
            aggregate += self.weights[idx] * self.states[idx]
        return aggregate


class HurstExponentAnalyzer:
    """Estimate Hurst exponent using rescaled range analysis."""

    def __init__(self, window: int = 100) -> None:
        self.window = int(window)
        self.returns: Deque[float] = deque(maxlen=self.window)

    def _rs(self, series: NDArray[np.float64]) -> float:
        if series.size < 2:
            return 0.0
        mean = float(np.mean(series))
        cumulative = np.cumsum(series - mean)
        R = float(np.max(cumulative) - np.min(cumulative))
        S = float(np.std(series, ddof=1))
        if S < EPS:
            return 0.5
        return R / S

    def estimate(self) -> float:
        if len(self.returns) < 20:
            return 0.5
        samples = np.fromiter(self.returns, dtype=float)
        candidate_lags = np.array([10, 20, 30, 50, samples.size // 2], dtype=int)
        lags = candidate_lags[candidate_lags < samples.size]
        rs_values: list[float] = []
        log_lags: list[float] = []
        for lag in lags:
            chunk_count = samples.size // lag
            if chunk_count < 2:
                continue
            chunk_rs: list[float] = []
            for idx in range(chunk_count):
                chunk = samples[idx * lag : (idx + 1) * lag]
                if chunk.size > 1:
                    chunk_rs.append(self._rs(chunk))
            if chunk_rs:
                rs_values.append(float(np.mean(chunk_rs)))
                log_lags.append(float(np.log(lag)))
        if len(log_lags) < 2:
            return 0.5
        slope = float(np.polyfit(log_lags, np.log(rs_values), 1)[0])
        return float(np.clip(slope, 0.0, 1.0))

    def update(self, ret: float) -> Dict[str, float]:
        self.returns.append(float(ret))
        hurst = self.estimate()
        if abs(hurst - 0.5) < 0.1:
            acf_like = 0.0
        elif hurst > 0.55:
            acf_like = min(0.5, (hurst - 0.5) * 2)
        else:
            acf_like = max(-0.3, (hurst - 0.5) * 2)
        return {"hurst": hurst, "acf_like": float(acf_like)}


class SpectralAnalyzer:
    """Dominant frequency detection for price oscillations."""

    def __init__(self, window: int = 64) -> None:
        self.window = int(window)
        self.prices: Deque[float] = deque(maxlen=self.window)

    def update(self, price: float) -> Dict[str, float]:
        self.prices.append(float(price))
        if len(self.prices) < 16:
            return {"dominant_freq": 0.0, "spectral_power": 1.0}
        values = np.fromiter(self.prices, dtype=float)
        detrended = detrend(values)
        fft = np.fft.rfft(detrended)
        power = np.square(np.abs(fft))
        frequencies = np.fft.rfftfreq(detrended.size)
        power[0] = 0.0
        if np.max(power, initial=0.0) < EPS:
            return {"dominant_freq": 0.0, "spectral_power": 1.0}
        idx = int(np.argmax(power[1:]) + 1)
        return {
            "dominant_freq": float(frequencies[idx]),
            "spectral_power": float(power[idx] / (np.sum(power) + EPS)),
        }


class SimpleEMD:
    """Simple empirical mode decomposition via polynomial trend approximation."""

    def __init__(self, window: int = 50) -> None:
        self.window = int(window)
        self.prices: Deque[float] = deque(maxlen=self.window)

    def update(self, price: float) -> Dict[str, float]:
        self.prices.append(float(price))
        if len(self.prices) < 5:
            return {"trend_vol": 0.0, "noise_vol": 0.0, "snr_db": 0.0}
        p = np.fromiter(self.prices, dtype=float)
        t = np.arange(p.size)
        coeffs = np.polyfit(t, p, 2)
        trend = np.polyval(coeffs, t)
        noise = p - trend
        if trend.size > 1:
            trend_vol = float(np.std(np.diff(trend)))
            noise_vol = float(np.std(noise))
            ratio = (trend_vol**2) / (noise_vol**2 + EPS)
            snr = 10.0 * np.log10(ratio + EPS)
        else:
            trend_vol = noise_vol = snr = 0.0
        return {"trend_vol": trend_vol, "noise_vol": noise_vol, "snr_db": snr}


class AdvancedRegimeDetector:
    """Blend multiple analyzers to infer the active market regime."""

    def __init__(self, *, window: int = 80) -> None:
        self.hurst = HurstExponentAnalyzer(window=100)
        self.spectral = SpectralAnalyzer(window=64)
        self.emd = SimpleEMD(window=window)
        self._last_price: float | None = None

    def update(self, price: float) -> Dict[str, float]:
        previous_price = self._last_price
        self._last_price = float(price)
        base = 1.0 if previous_price in (None, 0.0) else float(previous_price)
        ret = (self._last_price - (previous_price or self._last_price)) / base
        hurst_stats = self.hurst.update(ret)
        spectral_stats = self.spectral.update(self._last_price)
        emd_stats = self.emd.update(self._last_price)
        hurst_value = hurst_stats["hurst"]
        spectral_power = spectral_stats["spectral_power"]
        snr_db = emd_stats["snr_db"]
        trending = (hurst_value > 0.55) * 0.4 + (spectral_power > 0.25) * 0.3 + (snr_db > 5) * 0.3
        reverting = (hurst_value < 0.45) * 0.4 + (spectral_power < 0.2) * 0.3 + (snr_db < -5) * 0.3
        noise = (0.45 <= hurst_value <= 0.55) * 0.5 + (0.15 <= spectral_power <= 0.3) * 0.5
        scores = {
            Regime.TRENDING.value: trending,
            Regime.MEAN_REVERTING.value: reverting,
            Regime.NOISE.value: noise,
        }
        regime = max(scores, key=scores.get)
        return {
            "regime": regime,
            "confidence": float(scores[regime]),
            "hurst": hurst_value,
            "spectral_power": spectral_power,
            "snr_db": snr_db,
        }


@dataclass(slots=True)
class SigmaConfig:
    """Configuration parameters for :class:`SigmaController`."""

    entropy_target: float = 0.62
    tau_lr: float = 0.015
    window: int = 500


class SigmaController:
    """Monitor calibration metrics and adapt the risk multiplier τ."""

    def __init__(self, *, entropy_target: float, tau_lr: float, window: int) -> None:
        self.entropy_target = float(entropy_target)
        self.tau_lr = float(tau_lr)
        self.window = int(window)
        self.tau = 1.0
        self.probs: Deque[float] = deque(maxlen=self.window)
        self.targets: Deque[int] = deque(maxlen=self.window)
        self.entropy_hist: Deque[float] = deque(maxlen=self.window)

    def update(self, prob: float, target: int) -> None:
        probability = float(np.clip(prob, EPS_PROB_CLIP, 1.0 - EPS_PROB_CLIP))
        self.probs.append(probability)
        self.targets.append(int(target))

    def compute_entropy(self) -> float:
        if len(self.probs) < 2:
            return self.entropy_target
        probs = np.fromiter(self.probs, dtype=float)
        p_up = float(np.mean(probs > 0.5))
        p_down = 1.0 - p_up
        if p_up < EPS or p_down < EPS:
            return 0.0
        entropy = -(p_up * np.log(p_up + EPS) + p_down * np.log(p_down + EPS))
        return float(entropy / np.log(2))

    def brier_score(self) -> float:
        if not self.probs:
            return 0.25
        p = np.fromiter(self.probs, dtype=float)
        y = np.fromiter(self.targets, dtype=int)
        return float(np.mean(np.square(p - y)))

    def ece(self, *, n_bins: int = 10) -> float:
        if len(self.probs) < n_bins:
            return 0.0
        p = np.fromiter(self.probs, dtype=float)
        y = np.fromiter(self.targets, dtype=int)
        edges = np.linspace(0.0, 1.0, n_bins + 1)
        ece_value = 0.0
        for idx in range(n_bins):
            mask = (p >= edges[idx]) & (p < edges[idx + 1])
            count = int(np.sum(mask))
            if count == 0:
                continue
            accuracy = float(np.mean(y[mask]))
            confidence = float(np.mean(p[mask]))
            ece_value += abs(accuracy - confidence) * (count / p.size)
        return float(ece_value)

    def update_tau(self) -> None:
        entropy = self.compute_entropy()
        error = entropy - self.entropy_target
        self.tau *= 1.0 + self.tau_lr * error
        self.tau = float(np.clip(self.tau, TAU_MIN, TAU_MAX))
        self.entropy_hist.append(entropy)

    def audit(self) -> Dict[str, float | bool | int]:
        return {
            "brier": self.brier_score(),
            "ece": self.ece(),
            "entropy": self.compute_entropy(),
            "tau": self.tau,
            "n_obs": len(self.probs),
            "calibrated": self.ece() < 0.1,
        }


class PositionSizer:
    """Kelly-inspired position sizing with volatility modulation."""

    def __init__(self, *, kelly_fraction: float, leverage: float) -> None:
        self.kelly_fraction = float(kelly_fraction)
        self.leverage = float(leverage)

    def size(self, *, prob_up: float, volatility: float, scale: float) -> float:
        p = float(np.clip(prob_up, EPS_PROB_CLIP, 1.0 - EPS_PROB_CLIP))
        q = 1.0 - p
        b = 1.0 / max(0.01, volatility)
        raw_kelly = (p * b - q) / b if b > 0 else 0.0
        position = (
            float(np.clip(raw_kelly, -1.0, 1.0)) * self.kelly_fraction * scale * self.leverage
        )
        return float(np.clip(position, -1.0, 1.0))


class MultiScaleRiskMonitor:
    """Track drawdowns across multiple horizons."""

    def __init__(self, *, windows: Tuple[int, ...] = (20, 50, 200)) -> None:
        self.windows = windows
        self.equity: Deque[float] = deque(maxlen=max(windows))
        self.peak = 1.0

    def update(self, equity: float) -> Dict[str, float]:
        self.peak = max(self.peak, equity)
        self.equity.append(float(equity))
        current_dd = (self.peak - equity) / self.peak if self.peak > 0 else 0.0
        result: Dict[str, float] = {
            "current_dd": float(current_dd),
            "peak": float(self.peak),
        }
        for window in self.windows:
            if len(self.equity) >= window:
                recent = list(self.equity)[-window:]
                peak = float(np.max(recent))
                trough = float(np.min(recent))
                result[f"dd_{window}"] = (peak - trough) / peak if peak > 0 else 0.0
        return result


@dataclass(slots=True)
class FETEConfig:
    """Configuration surface for :class:`FETE`."""

    entropy_target: float = 0.62
    tau_lr: float = 0.015
    kelly_fraction: float = 0.25
    regime_weight: float = 0.35
    transaction_cost: float = 0.0002
    regime_window: int = 80
    leverage: float = 1.0


class FETE:
    """Fractal Ethical Trading Engine orchestrating analytics and risk control."""

    def __init__(self, config: FETEConfig | None = None) -> None:
        self.cfg = config or FETEConfig()
        self.regime_detector = AdvancedRegimeDetector(window=self.cfg.regime_window)
        self.position_sizer = PositionSizer(
            kelly_fraction=self.cfg.kelly_fraction, leverage=self.cfg.leverage
        )
        self.sigma = SigmaController(
            entropy_target=self.cfg.entropy_target,
            tau_lr=self.cfg.tau_lr,
            window=500,
        )
        self.risk_monitor = MultiScaleRiskMonitor()
        self.price_history: list[float] = []
        self.position_history: list[float] = []
        self.pnl_history: list[float] = []
        self.regime_history: list[str] = []
        self.tau_history: list[float] = []

    @staticmethod
    def _regime_scale(regime: str) -> float:
        return {
            Regime.TRENDING.value: 1.2,
            Regime.MEAN_REVERTING.value: 0.7,
            Regime.NOISE.value: 0.5,
        }.get(regime, 0.3)

    def decide(
        self,
        *,
        prob_up: float,
        price: float,
        equity: float = 1.0,
        realized_return: float | None = None,
    ) -> tuple[float, Dict[str, float]]:
        probability = float(np.clip(prob_up, EPS_PROB_CLIP, 1.0 - EPS_PROB_CLIP))
        regime_stats = self.regime_detector.update(price)
        regime = regime_stats["regime"]
        risk_stats = self.risk_monitor.update(equity)
        dd_penalty = max(0.1, 1.0 - risk_stats["current_dd"])
        vol_estimate = max(0.01, abs(regime_stats.get("snr_db", 0.0)) / 20.0)
        position = self.position_sizer.size(
            prob_up=probability,
            volatility=vol_estimate,
            scale=self._regime_scale(regime) * dd_penalty * self.sigma.tau,
        )
        if realized_return is not None:
            outcome = 1 if realized_return > 0 else 0
            self.sigma.update(probability, outcome)
            self.sigma.update_tau()
            self.price_history.append(price)
            self.position_history.append(position)
            self.pnl_history.append(
                position * realized_return - self.cfg.transaction_cost * abs(position)
            )
            self.regime_history.append(regime)
            self.tau_history.append(self.sigma.tau)
        return position, {
            "p_up": probability,
            "position": position,
            "regime": regime,
            "regime_scale": self._regime_scale(regime),
            "dd_penalty": dd_penalty,
            "current_dd": risk_stats["current_dd"],
            "tau": self.sigma.tau,
            "hurst": regime_stats.get("hurst", 0.0),
            "spectral_power": regime_stats.get("spectral_power", 0.0),
        }

    def backtest(self, prices: ArrayLike, model_probs: ArrayLike) -> Dict[str, object]:
        price_array = np.asarray(prices, dtype=float)
        prob_array = np.asarray(model_probs, dtype=float)
        if price_array.size < 2:
            raise ValueError("Backtest requires at least two price points")
        returns = np.diff(price_array) / price_array[:-1]
        if prob_array.size > returns.size:
            prob_array = prob_array[: returns.size]
        elif prob_array.size < returns.size:
            pad = returns.size - prob_array.size
            prob_array = np.pad(prob_array, (0, pad), constant_values=0.5)
        equity = 1.0
        equity_curve = [equity]
        for idx, ret in enumerate(returns):
            position, _ = self.decide(
                prob_up=float(prob_array[idx]),
                price=float(price_array[idx]),
                equity=equity,
                realized_return=float(ret),
            )
            pnl = position * ret - self.cfg.transaction_cost * abs(position)
            equity *= 1.0 + pnl
            equity_curve.append(equity)
        equity_array = np.asarray(equity_curve[1:], dtype=float)
        if equity_array.size > 1:
            eq_returns = np.diff(equity_array) / equity_array[:-1]
        else:
            eq_returns = np.array([0.0], dtype=float)
        sharpe = 0.0
        if eq_returns.size > 2 and np.std(eq_returns) > 0:
            sharpe = float(
                np.sqrt(252.0)
                * (np.mean(eq_returns) - (0.02 / 252.0))
                / (np.std(eq_returns) + 1e-12)
            )
        max_dd = 0.0
        if equity_array.size > 1:
            peaks = np.maximum.accumulate(equity_array)
            drawdowns = 1.0 - equity_array / peaks
            max_dd = float(np.max(drawdowns))
        return {
            "prices": price_array,
            "returns": returns,
            "equity": equity_array,
            "final_return": (float((equity_array[-1] - 1.0) * 100) if equity_array.size else 0.0),
            "positions": np.asarray(self.position_history, dtype=float),
            "regimes": list(self.regime_history),
            "audit": self.sigma.audit(),
            "sharpe": sharpe,
            "max_dd": max_dd,
        }


__all__ = [
    "FETE",
    "FETEConfig",
    "Regime",
    "HurstExponentAnalyzer",
    "SpectralAnalyzer",
    "SimpleEMD",
    "AdvancedRegimeDetector",
    "SigmaController",
    "SigmaConfig",
    "PositionSizer",
    "MultiScaleRiskMonitor",
    "binary_entropy",
    "FractalEMA",
]
