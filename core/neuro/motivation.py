"""Fractal motivation controllers and monitoring utilities.

The module integrates biologically inspired reward modulation into
TradePulse's neuroeconomic stack.  It blends fractal stochasticity,
reward-prediction errors, and adaptive exploration policies for
real-time strategy routing.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import Mapping, MutableMapping, Sequence

import numpy as np
from scipy.integrate import odeint

from core.neuro.fractal import FractalSummary, summarise_fractal_properties


def _softmax(values: np.ndarray) -> np.ndarray:
    """Numerically stable softmax using NumPy."""

    shifted = values - np.max(values)
    exp = np.exp(shifted)
    denom = exp.sum()
    if not np.isfinite(denom):
        return np.full_like(exp, 1.0 / exp.size)
    return exp / denom


class FractalBandit:
    """Thompson-sampling multi-armed bandit modulated by fractal dynamics."""

    def __init__(
        self,
        strategies: Sequence[str],
        *,
        hurst_exponent: float = 0.7,
        seed: int | None = None,
    ) -> None:
        if not strategies:
            raise ValueError("strategies must be a non-empty sequence")
        self.strategies = tuple(strategies)
        self.hurst = float(hurst_exponent)
        self._rng = np.random.default_rng(seed)
        self._alpha = np.ones(len(self.strategies), dtype=float)
        self._beta = np.ones(len(self.strategies), dtype=float)

    def select_strategy(self, motivation_signal: float) -> str:
        """Sample a strategy conditioned on the current motivation signal."""

        scaled_alpha = self._alpha * (1.0 + self.hurst * motivation_signal)
        scaled_beta = self._beta * (1.0 + self.hurst * motivation_signal)
        samples = self._rng.beta(scaled_alpha, scaled_beta)
        return self.strategies[int(np.argmax(samples))]

    def update(self, strategy_idx: int, reward: float) -> None:
        """Update the Beta posterior for ``strategy_idx`` with ``reward``."""

        if strategy_idx < 0 or strategy_idx >= len(self.strategies):
            raise IndexError("strategy_idx out of range")
        reward_clipped = float(np.clip(reward, 0.0, 1.0))
        self._alpha[strategy_idx] += reward_clipped
        self._beta[strategy_idx] += 1.0 - reward_clipped


class FractalMotivationEngine:
    """Combine information gain, coherence, and fractal noise into a signal."""

    def __init__(self, *, state_dim: int = 4) -> None:
        if state_dim <= 0:
            raise ValueError("state_dim must be positive")
        self.state_dim = state_dim
        self.temporal_scales = (1, 4, 16, 64)
        self._latest_summary: FractalSummary | None = None
        self.strategy_bandit = FractalBandit(
            ("exploit", "explore", "deepen", "broaden")
        )

    @property
    def latest_fractal_metrics(self) -> Mapping[str, float]:
        if self._latest_summary is None:
            return {
                "hurst": 0.5,
                "fractal_dim": 1.5,
                "volatility": 0.0,
                "scaling_exponent": 0.5,
                "stability": 1.0,
                "energy": 0.0,
            }
        return dict(self._latest_summary.as_mapping())

    def _compute_information_gain(
        self, current: np.ndarray, previous: np.ndarray | None
    ) -> float:
        current_arr = np.asarray(current, dtype=float)
        current_probs = _softmax(current_arr)
        if previous is None:
            prev_probs = np.full_like(current_probs, 1.0 / current_probs.size)
        else:
            prev_probs = _softmax(np.asarray(previous, dtype=float))

        eps = 1e-12
        kl = np.sum(
            prev_probs
            * (np.log(prev_probs + eps) - np.log(current_probs + eps))
        )
        return float(max(kl, 0.0))

    def _compute_context_coherence(self, hidden_states: np.ndarray) -> float:
        tensor = np.atleast_2d(np.asarray(hidden_states, dtype=float))
        norm = np.linalg.norm(tensor, axis=-1, keepdims=True) + 1e-8
        sim = (tensor @ tensor.T) / (norm * norm.transpose(0, 1))
        return float(np.mean(sim))

    def _motivation_policy(
        self, info_gain: float, context_coherence: float, fractal_state: float
    ) -> float:
        return 0.4 * info_gain + 0.4 * context_coherence + 0.2 * fractal_state

    def compute_contextual_motivation(
        self,
        *,
        hidden_states: np.ndarray,
        current: np.ndarray,
        previous: np.ndarray | None,
    ) -> float:
        info_gain = self._compute_information_gain(current, previous)
        coherence = self._compute_context_coherence(hidden_states)
        fractal_state = self._fractal_component(hidden_states)
        return float(self._motivation_policy(info_gain, coherence, fractal_state))

    def _fractal_component(self, hidden_states: np.ndarray) -> float:
        data = np.asarray(hidden_states, dtype=float)
        if data.ndim == 1:
            data = data[np.newaxis, :]

        summaries: list[FractalSummary] = []
        for row in data:
            try:
                summaries.append(summarise_fractal_properties(row))
            except ValueError:
                continue

        if not summaries:
            self._latest_summary = None
            return 0.0

        hurst = float(np.mean([summary.hurst for summary in summaries]))
        dimension = float(np.mean([summary.fractal_dimension for summary in summaries]))
        volatility = float(np.mean([summary.volatility for summary in summaries]))
        scaling = float(np.mean([summary.scaling_exponent for summary in summaries]))
        stability = float(np.mean([summary.stability for summary in summaries]))
        energy = float(np.mean([summary.energy for summary in summaries]))

        self._latest_summary = FractalSummary(
            hurst=hurst,
            fractal_dimension=dimension,
            volatility=volatility,
            scaling_exponent=scaling,
            stability=stability,
            energy=energy,
        )

        scaled_energy = energy / (1.0 + volatility)
        hurst_deviation = (hurst - 0.5) * 2.0
        fractal_state = stability * hurst_deviation + 0.1 * scaled_energy
        return float(fractal_state)


class AllostaticRegulator:
    """Simple ODE-based regulator capturing allostatic load dynamics."""

    def __init__(self) -> None:
        self.allostatic_load = 0.0
        self.dopamine_level = 0.5
        self.stress_level = 0.1

    def _ode(
        self, y: Sequence[float], _: float, rpe: float, stress_input: float
    ) -> list[float]:
        allostatic, dopamine, stress = y
        d_allostatic = -0.1 * allostatic + 0.2 * stress
        d_dopamine = rpe - 0.2 * dopamine
        d_stress = stress_input - 0.1 * stress
        return [d_allostatic, d_dopamine, d_stress]

    def update(
        self, rpe: float, stress_input: float, *, time_step: float = 0.1
    ) -> float:
        y0 = (self.allostatic_load, self.dopamine_level, self.stress_level)
        t = (0.0, time_step)
        result = odeint(
            self._ode, y0, t, args=(rpe, stress_input), atol=1e-6, rtol=1e-6
        )
        self.allostatic_load, self.dopamine_level, self.stress_level = map(
            float, result[-1]
        )
        self.allostatic_load = float(np.clip(self.allostatic_load, -1.0, 1.0))
        return self.allostatic_load


class ValuePredictor:
    """Lightweight predictor that avoids the PyTorch dependency for tests.

    Provides a deterministic linear projection over the state vector so callers
    still receive a stable, repeatable signal without requiring training.
    """

    def __init__(self, input_dim: int = 4, hidden_dim: int = 16) -> None:
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        # Deterministic ramped weights provide a stable, non-learning projection
        # without introducing randomness or an external dependency.
        weights = np.linspace(0.5, 1.0, num=self.input_dim, dtype=float)
        self._weights = weights / np.linalg.norm(weights)

    def __call__(self, state: np.ndarray) -> float:
        return self.forward(state)

    def forward(self, state: np.ndarray) -> float:
        tensor = np.asarray(state, dtype=float)
        if tensor.ndim == 1:
            tensor = tensor[np.newaxis, :]
        feature_dim = tensor.shape[-1]
        if feature_dim < self.input_dim:
            padding = np.zeros((tensor.shape[0], self.input_dim - feature_dim))
            tensor = np.concatenate((tensor, padding), axis=-1)
        elif feature_dim > self.input_dim:
            tensor = tensor[..., : self.input_dim]
        projected = tensor @ self._weights
        return float(np.mean(projected))


class RealTimeMotivationMonitor:
    """Lightweight telemetry for motivation stability and exploration balance."""

    def __init__(self, window: int = 64) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        self._signals = deque(maxlen=window)
        self._rewards = deque(maxlen=window)
        self._actions = deque(maxlen=window)
        self._score_means = deque(maxlen=window)

    def observe(
        self,
        motivation_signal: float,
        reward: float,
        scores: Mapping[str, float],
        action: str,
    ) -> dict[str, float]:
        self._signals.append(float(motivation_signal))
        self._rewards.append(float(reward))
        self._actions.append(action)
        mean_score = float(np.mean(list(scores.values())) if scores else 0.0)
        self._score_means.append(mean_score)

        return {
            "signal_mean": float(np.mean(self._signals)),
            "signal_std": float(np.std(self._signals)),
            "reward_mean": float(np.mean(self._rewards)),
            "score_mean": float(np.mean(self._score_means)),
            "action_entropy": float(self._action_entropy()),
        }

    def _action_entropy(self) -> float:
        if not self._actions:
            return 0.0
        counts = Counter(self._actions)
        if len(counts) <= 1:
            return 0.0
        total = sum(counts.values())
        probs = np.array([count / total for count in counts.values()], dtype=float)
        entropy = -np.sum(probs * np.log(probs + 1e-12))
        normalizer = math.log(len(counts))
        if normalizer <= 0.0:
            return 0.0
        return float(entropy / normalizer)


@dataclass(frozen=True)
class MotivationDecision:
    """Container for controller recommendations and telemetry snapshots."""

    action: str
    scores: Mapping[str, float]
    motivation_signal: float
    intrinsic_reward: float
    allostatic_load: float
    monitor_metrics: Mapping[str, float]


class FractalMotivationController:
    """Guard-rail aware controller that routes actions via fractal motivation."""

    def __init__(
        self, actions: Sequence[str], *, exploration_coef: float = 1.0
    ) -> None:
        if not actions:
            raise ValueError("actions must be a non-empty sequence")
        if "pause_and_audit" not in actions:
            actions = tuple(actions) + ("pause_and_audit",)
        self.actions = tuple(dict.fromkeys(actions))
        self.c = float(exploration_coef)
        self.counts: MutableMapping[str, int] = defaultdict(int)
        self.values: MutableMapping[str, float] = defaultdict(float)
        self.total_count = 0
        self.fractal_engine = FractalMotivationEngine(state_dim=len(self.actions))
        self.allostatic_reg = AllostaticRegulator()
        self.value_predictor = ValuePredictor(input_dim=4)
        self.monitor = RealTimeMotivationMonitor()
        self._previous_state: np.ndarray | None = None
        self._last_action: str | None = None
        self._strategy_actions = tuple(
            action
            for action in self.actions
            if action in {"exploit", "explore", "deepen", "broaden"}
        )
        bandit_actions = self._strategy_actions or (
            "exploit",
            "explore",
            "deepen",
            "broaden",
        )
        self._bandit = FractalBandit(bandit_actions)

    def recommend(
        self,
        *,
        state: Sequence[float],
        signals: Mapping[str, float | bool | int],
        next_state: Sequence[float] | None = None,
    ) -> MotivationDecision:
        guardrails_ok = bool(signals.get("risk_ok", True)) and bool(
            signals.get("compliance_ok", True)
        )
        if not guardrails_ok:
            scores = {action: -1e6 for action in self.actions}
            scores["pause_and_audit"] = 1e6
            metrics = self.monitor.observe(0.0, 0.0, scores, "pause_and_audit")
            self._last_action = "pause_and_audit"
            return MotivationDecision(
                action="pause_and_audit",
                scores=scores,
                motivation_signal=0.0,
                intrinsic_reward=0.0,
                allostatic_load=self.allostatic_reg.allostatic_load,
                monitor_metrics=metrics,
            )

        state_vec = self._coerce_state(state)
        hidden_states = self._build_hidden_states(state_vec)
        previous = self._previous_state
        motivation_signal = self.fractal_engine.compute_contextual_motivation(
            hidden_states=hidden_states,
            current=state_vec,
            previous=previous,
        )
        projected_next = (
            self._coerce_state(next_state)
            if next_state is not None
            else self._project_next_state(state_vec, signals)
        )
        intrinsic_reward, allostatic = self.compute_intrinsic_reward(
            state_vec, projected_next, motivation_signal
        )
        expected_rewards = {
            action: self._estimate_reward(
                action, signals, intrinsic_reward, motivation_signal
            )
            for action in self.actions
        }
        ucb_scores = self._compute_ucb_scores(expected_rewards, motivation_signal)

        if self._strategy_actions:
            strategy = self._bandit.select_strategy(motivation_signal)
            if strategy in ucb_scores:
                ucb_scores[strategy] += abs(motivation_signal)
        recommended = max(ucb_scores, key=ucb_scores.get)
        self._update_after_selection(recommended, expected_rewards[recommended])

        if self._strategy_actions and recommended in self._strategy_actions:
            idx = self._strategy_actions.index(recommended)
            reward_norm = float(
                np.clip((expected_rewards[recommended] + 1.0) / 2.0, 0.0, 1.0)
            )
            self._bandit.update(idx, reward_norm)

        metrics = self.monitor.observe(
            motivation_signal, expected_rewards[recommended], ucb_scores, recommended
        )
        self._previous_state = state_vec
        self._last_action = recommended

        return MotivationDecision(
            action=recommended,
            scores=dict(ucb_scores),
            motivation_signal=float(motivation_signal),
            intrinsic_reward=float(intrinsic_reward),
            allostatic_load=float(allostatic),
            monitor_metrics=dict(metrics),
        )

    def register_outcome(self, reward: float, action: str | None = None) -> None:
        target_action = action or self._last_action
        if not target_action or target_action not in self.actions:
            return
        self._update_after_selection(target_action, reward, increment_counts=False)

    def _coerce_state(self, state: Sequence[float]) -> np.ndarray:
        array = np.asarray(state, dtype=float)
        if array.ndim != 1:
            raise ValueError("state must be a 1D sequence")
        if array.size == 0:
            raise ValueError("state must not be empty")
        return array

    def _build_hidden_states(self, state: np.ndarray) -> np.ndarray:
        features = []
        for scale in self.fractal_engine.temporal_scales:
            if scale <= 1 or state.size < scale:
                features.append(state)
                continue
            kernel = np.ones(scale, dtype=float) / scale
            pooled = np.convolve(state, kernel, mode="valid")
            if pooled.size == 0:
                pooled = np.full_like(state, state.mean())
            pooled = np.pad(
                pooled,
                (0, max(0, state.size - pooled.size)),
                mode="edge",
            )
            features.append(pooled[: state.size])
        return np.stack(features, axis=0)

    def _project_next_state(
        self, state: np.ndarray, signals: Mapping[str, float | bool | int]
    ) -> np.ndarray:
        delta = np.zeros_like(state)
        mapping = [
            float(signals.get("PnL", 0.0)),
            float(signals.get("volatility", 0.0)),
            float(signals.get("trend_strength", 0.0)),
        ]
        for idx, value in enumerate(mapping):
            if idx < delta.size:
                delta[idx] = value
        if bool(signals.get("hazard", False)) and delta.size:
            delta[0] -= abs(float(signals.get("hazard_penalty", 1.0)))
        return state + delta

    def compute_intrinsic_reward(
        self, state: np.ndarray, next_state: np.ndarray, motivation_signal: float
    ) -> tuple[float, float]:
        predicted = self.value_predictor(state)
        actual = self.value_predictor(next_state)
        rpe = float(actual - predicted)
        info_gain = float(np.linalg.norm(next_state - state))
        metrics = self.fractal_engine.latest_fractal_metrics
        energy = metrics.get("energy", 0.0)
        intrinsic = rpe + 0.1 * info_gain + 0.05 * energy + 0.01 * motivation_signal
        allostatic = self.allostatic_reg.update(rpe, info_gain)
        modulation = max(0.0, 1.0 - abs(allostatic))
        return float(intrinsic * modulation), float(allostatic)

    def _estimate_reward(
        self,
        action: str,
        signals: Mapping[str, float | bool | int],
        intrinsic_reward: float,
        motivation_signal: float,
    ) -> float:
        pnl = float(signals.get("PnL", 0.0))
        reward = intrinsic_reward + pnl
        if bool(signals.get("hazard", False)) and action in {
            "exploit",
            "explore",
            "deepen",
            "broaden",
        }:
            reward -= 2.0
        if action == "pause_and_audit":
            if pnl <= 0.0:
                reward += 1.0
            else:
                reward -= 0.5
        if action == "stabilize":
            reward -= 0.1 * abs(motivation_signal)
        return float(reward)

    def _compute_ucb_scores(
        self, expected_rewards: Mapping[str, float], motivation_signal: float
    ) -> MutableMapping[str, float]:
        scores: MutableMapping[str, float] = {}
        total = max(1, self.total_count)
        log_total = math.log(total)
        for action, expected in expected_rewards.items():
            count = self.counts[action]
            if count == 0:
                bonus = self.c * (1.0 + abs(motivation_signal))
                scores[action] = expected + bonus
            else:
                bonus = self.c * math.sqrt((2.0 * log_total) / count)
                scores[action] = self.values[action] + bonus
            if action in {"exploit", "deepen"}:
                scores[action] += 0.25 * motivation_signal
            elif action == "explore":
                scores[action] += 0.15 * abs(motivation_signal)
        return scores

    def _update_after_selection(
        self, action: str, reward: float, *, increment_counts: bool = True
    ) -> None:
        if increment_counts:
            self.counts[action] += 1
            self.total_count += 1

        n = self.counts[action]
        if n <= 0:
            return

        value = self.values[action]
        self.values[action] = value + (reward - value) / n


__all__ = [
    "AllostaticRegulator",
    "FractalBandit",
    "FractalMotivationController",
    "FractalMotivationEngine",
    "MotivationDecision",
    "RealTimeMotivationMonitor",
    "ValuePredictor",
]
