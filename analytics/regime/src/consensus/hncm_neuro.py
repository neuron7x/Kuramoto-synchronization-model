# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Neuro-inspired consensus adapter for TradePulse.

Implements:
- Reward Prediction Error (RPE) with asymmetric learning rates (α+ / α−)
- Eligibility traces per agent (λ-trace)
- Metaplasticity (BCM-like sliding threshold on agent activation)
- Synaptic/homeostatic normalization with softmax temperature τ
- Noradrenergic-like change detection (Page–Hinkley) → adaptive α, τ, thresholds
- Consolidation (EWC-like) to prevent catastrophic forgetting
- Energy budget regularizer on weight updates
- Reliability calibration (precision weighting) from running Brier-like score

No external deps beyond stdlib. Compatible with TradePulse EWSResult and domain Signal.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Literal, Mapping, Optional, Tuple

Action = Literal["BUY", "SELL", "HOLD"]


# ---------- helpers ----------


def clamp(x: float, lo: float, hi: float) -> float:
    return x if (x >= lo and x <= hi) else (lo if x < lo else hi)


def ema(prev: float, value: float, alpha: float) -> float:
    return alpha * value + (1.0 - alpha) * prev


def softmax(d: Mapping[str, float], temperature: float) -> Dict[str, float]:
    """Numerically-stable softmax over values in d."""
    if not d:
        return {}
    t = max(1e-6, float(temperature))
    xs = list(d.values())
    m = max(xs)
    exps = {k: math.exp((v - m) / t) for k, v in d.items()}
    Z = sum(exps.values()) or 1.0
    return {k: v / Z for k, v in exps.items()}


# ---------- data ----------


@dataclass(slots=True, frozen=True)
class AgentVote:
    agent: str
    score: float  # [-1, 1]
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True, frozen=True)
class ConsensusDecision:
    action: Action
    score: float  # [-1,1]
    confidence: float  # [0,1]
    weights: Mapping[str, float]
    votes: Tuple[AgentVote, ...]


# ---------- state ----------

_DEFAULT_STATE = {
    "reward_ema": {},  # agent -> r ∈ [-1,1]
    "baseline_ema": 0.0,  # baseline outcome for RPE
    "activation_ma": {},  # agent -> mean |score|
    "eligibility": {},  # agent -> trace value
    "reliability": {},  # agent -> calibration [0,1] (lower = worse)
    "consolidated": {},  # agent -> last consolidated weight
    "ph": {"mean": 0.0, "m_t": 0.0, "T": 0},  # Page–Hinkley stats
    "last_weights": {},  # previous step effective weights
    "config": {},
}


class _State:
    def __init__(self, path: str | Path | None):
        self.path = Path(path or Path.home() / ".tradepulse" / "hncm_neuro_state.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.s = json.loads(json.dumps(_DEFAULT_STATE))  # deep copy
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text())
                # non-destructive update
                for k, v in loaded.items():
                    self.s[k] = v
            except Exception:
                backup = self.path.with_suffix(".corrupt.json")
                try:
                    self.path.replace(backup)
                except Exception:
                    pass

    def flush(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.s, indent=2))
        tmp.replace(self.path)


# ---------- core adapter ----------


class NeuroConsensusAdapter:
    """Neuro-inspired consensus with meta-plasticity and change detection.

    Parameters
    ----------
    base_weights: static priors per agent (default 1.0)
    buy_threshold, sell_threshold: action thresholds on aggregated score
    alpha_pos, alpha_neg: asymmetric learning rates for positive vs negative RPE
    lambda_trace: eligibility decay factor ∈ [0,1)
    alpha_baseline: EMA for baseline outcome (for RPE)
    tau: softmax temperature for weight normalization
    ph_delta, ph_lambda, ph_threshold: Page–Hinkley parameters
    energy_budget: L1 budget for |Δw| per step (if None → no budget)
    ewc_strength: consolidation penalty strength toward consolidated weights
    gamma_reward: exponent for reward→weight mapping (nonlinear contrast)
    """

    def __init__(
        self,
        *,
        base_weights: Optional[Mapping[str, float]] = None,
        buy_threshold: float = 0.2,
        sell_threshold: float = -0.2,
        alpha_pos: float = 0.3,
        alpha_neg: float = 0.1,
        lambda_trace: float = 0.8,
        alpha_baseline: float = 0.05,
        tau: float = 0.7,
        ph_delta: float = 0.01,
        ph_lambda: float = 0.02,
        ph_threshold: float = 0.15,
        energy_budget: Optional[float] = 0.6,
        ewc_strength: float = 0.02,
        gamma_reward: float = 1.2,
        state_path: Optional[str | Path] = None,
    ) -> None:
        self.base_weights: Dict[str, float] = dict(base_weights or {})
        self.buy_threshold = float(buy_threshold)
        self.sell_threshold = float(sell_threshold)
        self.alpha_pos = float(alpha_pos)
        self.alpha_neg = float(alpha_neg)
        self.lambda_trace = float(lambda_trace)
        self.alpha_baseline = float(alpha_baseline)
        self.tau = float(tau)
        self.ph_delta = float(ph_delta)
        self.ph_lambda = float(ph_lambda)
        self.ph_threshold = float(ph_threshold)
        self.energy_budget = energy_budget
        self.ewc_strength = float(ewc_strength)
        self.gamma_reward = float(gamma_reward)
        self.state = _State(state_path)

    # ----- aggregation -----

    @staticmethod
    def _effective_weights(
        base: Mapping[str, float],
        learned: Optional[Mapping[str, float]] = None,
        override: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, float]:
        w: Dict[str, float] = dict(base)
        if learned:
            learned_f = {k: max(0.0, float(v)) for k, v in learned.items()}
            total_learned = sum(learned_f.values())
            if total_learned > 0:
                prior_total = sum(float(w.get(k, 1.0)) for k in learned_f) or float(
                    len(learned_f)
                )
                scale = prior_total / total_learned
                for k, v in learned_f.items():
                    w[k] = v * scale
            else:
                for k in learned_f:
                    w[k] = 0.0
        if override:
            for k, v in override.items():
                w[k] = float(v)
        # floor to avoid zeroed agents
        for k in tuple(w.keys()):
            w[k] = max(0.0, float(w[k]))
        return w

    def aggregate(
        self,
        votes: Iterable[AgentVote],
        *,
        learned_weights: Optional[Mapping[str, float]] = None,
        override_weights: Optional[Mapping[str, float]] = None,
    ) -> Tuple[float, Dict[str, float]]:
        votes = tuple(votes)
        weights = self._effective_weights(
            self.base_weights, learned_weights, override_weights
        )
        num = 0.0
        den = 0.0
        for v in votes:
            s = clamp(float(v.score), -1.0, 1.0)
            c = clamp(float(v.confidence), 0.0, 1.0)
            w = float(weights.get(v.agent, 1.0))
            num += w * c * s
            den += w * c
        agg = (num / den) if den > 0 else 0.0
        agg = clamp(agg, -1.0, 1.0)
        return agg, weights

    def score_to_action(self, score: float) -> Action:
        if score >= self.buy_threshold:
            return "BUY"
        if score <= self.sell_threshold:
            return "SELL"
        return "HOLD"

    @staticmethod
    def confidence_from_score(score: float) -> float:
        return abs(clamp(score, -1.0, 1.0))

    # ----- learned weights (neuro) -----

    def _metaplasticity_gain(self, agent: str, score_abs: float) -> float:
        # BCM-like sliding threshold: potentiation favored when |score| exceeds its running mean
        theta = float(self.state.s["activation_ma"].get(agent, 0.3))
        # gain grows with margin above theta, capped
        margin = max(0.0, score_abs - theta)
        return clamp(1.0 + 1.5 * margin, 0.5, 2.5)

    def _update_activation_ma(
        self, agent: str, score_abs: float, alpha: float = 0.05
    ) -> None:
        prev = float(self.state.s["activation_ma"].get(agent, 0.3))
        self.state.s["activation_ma"][agent] = clamp(
            ema(prev, score_abs, alpha), 0.0, 1.0
        )

    def _update_eligibility(self, agent: str, score: float) -> float:
        e_prev = float(self.state.s["eligibility"].get(agent, 0.0))
        e_new = self.lambda_trace * e_prev + float(score)
        self.state.s["eligibility"][agent] = clamp(e_new, -5.0, 5.0)
        return self.state.s["eligibility"][agent]

    def _update_reliability(
        self, agent: str, realized: float, score: float, beta: float = 0.05
    ) -> None:
        """Running calibration proxy: lower error → higher reliability."""
        # Expected sign = sign(score), target = sign(realized)
        # error in [0,1]: 0 when aligned, 1 when opposite; neutral 0.5 if score≈0
        if abs(score) < 1e-6:
            err = 0.5
        else:
            err = 0.0 if realized * score >= 0 else 1.0
        rel_prev = float(self.state.s["reliability"].get(agent, 0.5))
        rel_new = clamp(ema(rel_prev, 1.0 - err, beta), 0.0, 1.0)
        self.state.s["reliability"][agent] = rel_new

    def _page_hinkley_update(self, x_t: float) -> bool:
        """Return True if change detected."""
        ph = self.state.s["ph"]
        mean = float(ph.get("mean", 0.0))
        T = int(ph.get("T", 0)) + 1
        mean_new = mean + (x_t - mean) / T
        m_t = float(ph.get("m_t", 0.0))
        # cumulative mean centered variable
        m_t = (1 - self.ph_lambda) * m_t + (x_t - mean_new - self.ph_delta)
        self.state.s["ph"] = {"mean": mean_new, "m_t": m_t, "T": T}
        return m_t < -self.ph_threshold or m_t > self.ph_threshold

    def _consolidate(self, weights: Mapping[str, float], beta: float = 0.01) -> None:
        """Slowly move consolidated weights toward current weights (late-phase capture)."""
        cons = self.state.s["consolidated"]
        for k, w in weights.items():
            prev = float(cons.get(k, w))
            cons[k] = (1 - beta) * prev + beta * float(w)

    def _apply_energy_budget(
        self, old: Mapping[str, float], new: Dict[str, float]
    ) -> Dict[str, float]:
        if self.energy_budget is None:
            return new
        budget = float(self.energy_budget)
        total_delta = sum(
            abs(float(new.get(k, 0.0)) - float(old.get(k, 0.0)))
            for k in set(old) | set(new)
        )
        if total_delta <= budget or total_delta == 0.0:
            return new
        # scale down deltas to fit budget
        scale = budget / total_delta
        out = {}
        for k in set(old) | set(new):
            o = float(old.get(k, 0.0))
            n = float(new.get(k, 0.0))
            out[k] = o + (n - o) * scale
        return out

    def _r_to_preweight(self, r: float) -> float:
        # map [-1,1] → [eps, 1] with contrast gamma
        x = clamp((r + 1.0) / 2.0, 0.0, 1.0)
        return max(1e-3, x**self.gamma_reward)

    def learned_weights(self) -> Dict[str, float]:
        rewards: Mapping[str, float] = self.state.s.get("reward_ema", {})
        rel: Mapping[str, float] = self.state.s.get("reliability", {})
        pre = {
            k: self._r_to_preweight(float(v)) * max(0.1, float(rel.get(k, 0.5)))
            for k, v in rewards.items()
        }
        if not pre:
            return {}
        w_soft = softmax(pre, self.tau)
        # regularize toward consolidated weights (EWC-like)
        cons = self.state.s.get("consolidated", {})
        if cons and self.ewc_strength > 0:
            w_out = {}
            for k in set(pre) | set(cons):
                p = float(w_soft.get(k, 0.0))
                c = float(cons.get(k, p))
                w_out[k] = clamp(
                    (1 - self.ewc_strength) * p + self.ewc_strength * c, 0.0, 1.0
                )
            w_soft = w_out
        # ensure normalization
        s = sum(w_soft.values()) or 1.0
        return {k: v / s for k, v in w_soft.items()}

    # ----- main API -----

    def decide(
        self,
        votes: Iterable[AgentVote],
        *,
        override_weights: Optional[Mapping[str, float]] = None,
        learned_weights: Optional[Mapping[str, float]] = None,
    ) -> ConsensusDecision:
        votes = tuple(votes)
        # use current learned weights if not provided
        lw = dict(learned_weights or self.learned_weights())
        score, weights = self.aggregate(
            votes, learned_weights=lw, override_weights=override_weights
        )
        action: Action = self.score_to_action(score)
        conf = self.confidence_from_score(score)
        # persist last weights
        self.state.s["last_weights"] = dict(weights)
        return ConsensusDecision(
            action=action, score=score, confidence=conf, weights=weights, votes=votes
        )

    def update_feedback(
        self, realized: float, agent_scores: Mapping[str, float]
    ) -> Dict[str, float]:
        """Neuro-inspired weight learning from outcome and agent scores.

        realized ∈ [-1,1], agent_scores: {agent: score∈[-1,1]} from the decision timestep.
        """
        r = clamp(float(realized), -1.0, 1.0)
        # update baseline and compute RPE
        baseline = float(self.state.s.get("baseline_ema", 0.0))
        baseline_new = ema(baseline, r, self.alpha_baseline)
        rpe = r - baseline_new
        self.state.s["baseline_ema"] = clamp(baseline_new, -1.0, 1.0)

        # change detection → adaptive α, τ (arousal)
        change = self._page_hinkley_update(r)
        alpha_pos = self.alpha_pos * (1.5 if change else 1.0)
        alpha_neg = self.alpha_neg * (1.5 if change else 1.0)
        self.tau = clamp(self.tau * (0.8 if change else 1.0), 0.3, 1.5)

        # update per-agent stats and rewards
        rewards = self.state.s["reward_ema"]
        for agent, s in agent_scores.items():
            s = clamp(float(s), -1.0, 1.0)
            self._update_activation_ma(agent, abs(s))
            e = self._update_eligibility(agent, s)
            gain = self._metaplasticity_gain(agent, abs(s))
            lr = alpha_pos if (rpe * s) >= 0 else alpha_neg
            prev = float(rewards.get(agent, 0.0))
            # Hebbian-like: Δ ∝ RPE × eligibility × gain
            delta = lr * rpe * e * gain
            new_r = clamp(prev + delta, -1.0, 1.0)
            rewards[agent] = new_r
            self._update_reliability(agent, r, s)

        # compute learned weights with normalization & consolidation
        new_weights = self.learned_weights()
        # apply energy budget vs last weights
        last_w = self.state.s.get("last_weights", {})
        new_weights = self._apply_energy_budget(last_w, dict(new_weights))
        # consolidate slowly
        self._consolidate(new_weights)

        self.state.flush()
        return dict(new_weights)
