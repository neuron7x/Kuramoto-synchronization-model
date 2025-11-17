# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""HNCM-style adaptive consensus for TradePulse.

Адаптивний шар колективного інтелекту:
- Зважене середнє агентних оцінок у [-1,1] з урахуванням впевненості [0,1].
- Онлайн-навчання ваг з EMA за реалізованим результатом (PnL/accuracy у [-1,1]).
- Сумісне з :mod:`analytics.regime.src.core.ews` (EWSResult) та :mod:`domain.signals`.

Залежності: тільки стандартна бібліотека + існуючі модулі TradePulse.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Literal, Mapping, Optional, Tuple

# ----- helpers -----


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp ``x`` into the inclusive ``[lo, hi]`` interval."""

    return max(lo, min(hi, x))


def ema(prev: float, value: float, alpha: float) -> float:
    """Return an exponential moving average step."""

    return alpha * value + (1.0 - alpha) * prev


Action = Literal["BUY", "SELL", "HOLD"]


@dataclass(slots=True, frozen=True)
class AgentVote:
    """Окремий голос агента."""

    agent: str
    score: float  # [-1, 1]; >0 -> buy, <0 -> sell
    confidence: float = 1.0  # [0, 1]
    rationale: str = ""


@dataclass(slots=True, frozen=True)
class ConsensusDecision:
    """Рішення консенсусу."""

    action: Action
    score: float
    confidence: float
    weights: Mapping[str, float]
    votes: Tuple[AgentVote, ...]


class _StateStore:
    """Проста JSON-пам'ять для нагород/ваг (атомарний запис)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or Path.home() / ".tradepulse" / "hncm_state.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state: Dict[str, Any] = self._fresh_state()
        self._load()

    def _fresh_state(self) -> Dict[str, Any]:
        return {"reward_ema": {}, "agent_weights": {}}

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(
                raw, Mapping
            ):  # pragma: no cover - defensive, asserted in tests
                raise TypeError("state must be a mapping")
        except Exception:
            # якщо файл пошкоджено — зберегти як .corrupt.json і почати заново
            try:
                self.path.replace(self.path.with_suffix(".corrupt.json"))
            finally:
                self.state = self._fresh_state()
            return

        reward = raw.get("reward_ema", {})
        weights = raw.get("agent_weights", {})
        if not isinstance(reward, Mapping) or not isinstance(weights, Mapping):
            self.state = self._fresh_state()
            return
        self.state = {
            "reward_ema": {str(k): float(v) for k, v in reward.items()},
            "agent_weights": {str(k): max(0.0, float(v)) for k, v in weights.items()},
        }

    def get_reward(self, agent: str) -> float:
        return float(self.state.get("reward_ema", {}).get(agent, 0.0))

    def set_reward(self, agent: str, value: float) -> None:
        self.state.setdefault("reward_ema", {})[agent] = float(value)

    def get_weight(self, agent: str) -> float:
        return float(self.state.get("agent_weights", {}).get(agent, 1.0))

    def set_weight(self, agent: str, value: float) -> None:
        self.state.setdefault("agent_weights", {})[agent] = max(0.0, float(value))

    def flush(self) -> None:
        payload = json.dumps(self.state, indent=2, sort_keys=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.replace(self.path)


class HNCMConsensusAdapter:
    """Адаптивний консенсус (HNCM v1.1 логіка) для TradePulse.

    Parameters
    ----------
    base_weights: Optional[Mapping[str, float]]
        Статичні ваги агентів (за замовчуванням 1.0).
    alpha: float
        EMA-сгладжування для оновлення нагород (0<alpha≤1).
    state_path: Optional[str|Path]
        Шлях до JSON зі станом (за замовчуванням ~/.tradepulse/hncm_state.json).
    buy_threshold, sell_threshold: float
        Пороги картографування score→BUY/SELL; інакше HOLD.
    """

    def __init__(
        self,
        *,
        base_weights: Optional[Mapping[str, float]] = None,
        alpha: float = 0.2,
        state_path: Optional[str | Path] = None,
        buy_threshold: float = 0.15,
        sell_threshold: float = -0.15,
    ) -> None:
        self.base_weights: Dict[str, float] = self._validate_base_weights(
            base_weights or {}
        )
        self.alpha = self._validate_alpha(alpha)
        self.store = _StateStore(state_path)
        self.buy_threshold, self.sell_threshold = self._validate_thresholds(
            buy_threshold, sell_threshold
        )

    # ---------- aggregation ----------

    @staticmethod
    def _effective_weights(
        base: Mapping[str, float],
        learned: Optional[Mapping[str, float]] = None,
        override: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, float]:
        w: Dict[str, float] = dict(base)
        if learned:
            for k, v in learned.items():
                w[k] = max(0.0, float(v))
        if override:
            for k, v in override.items():
                w[k] = float(v)
        for k in tuple(w.keys()):
            w[k] = max(0.0, float(w[k]))
        return w

    @staticmethod
    def _validate_base_weights(weights: Mapping[str, float]) -> Dict[str, float]:
        validated: Dict[str, float] = {}
        for agent, value in weights.items():
            v = float(value)
            if v < 0.0:
                raise ValueError(
                    f"base weight for agent '{agent}' must be non-negative"
                )
            validated[str(agent)] = v
        return validated

    @staticmethod
    def _validate_alpha(alpha: float) -> float:
        a = float(alpha)
        if not 0.0 < a <= 1.0:
            raise ValueError("alpha must be in the interval (0, 1]")
        return a

    @staticmethod
    def _validate_thresholds(
        buy_threshold: float, sell_threshold: float
    ) -> Tuple[float, float]:
        buy = float(buy_threshold)
        sell = float(sell_threshold)
        if not -1.0 <= sell <= buy <= 1.0:
            raise ValueError("thresholds must satisfy -1 <= sell <= buy <= 1")
        return buy, sell

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
        for vote in votes:
            weights.setdefault(
                vote.agent, max(0.0, float(self.base_weights.get(vote.agent, 1.0)))
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
        return clamp(agg, -1.0, 1.0), weights

    # ---------- mapping ----------

    def score_to_action(self, score: float) -> Action:
        s = float(score)
        if s >= self.buy_threshold:
            return "BUY"
        if s <= self.sell_threshold:
            return "SELL"
        return "HOLD"

    def confidence_from_score(self, score: float) -> float:
        return abs(clamp(score, -1.0, 1.0))

    # ---------- online learning ----------

    def update_feedback(
        self, realized: float, agent_scores: Mapping[str, float]
    ) -> Dict[str, float]:
        """Оновити EMA-нагороди агентів згідно з реалізованим результатом.

        realized: нормалізований результат у [-1,1] (знакований PnL/accuracy)
        agent_scores: оцінки агентів у [-1,1] на момент рішення
        """
        r = clamp(float(realized), -1.0, 1.0)
        for agent, s in agent_scores.items():
            prev = self.store.get_reward(agent)
            new_r = ema(prev, r * clamp(float(s), -1.0, 1.0), self.alpha)
            self.store.set_reward(agent, clamp(new_r, -1.0, 1.0))
        self.store.flush()
        return self.learned_weights()

    def learned_weights(self) -> Dict[str, float]:
        rewards: Mapping[str, float] = self.store.state.get("reward_ema", {})
        # відображення [-1,1] → [0.05,1.0]
        return {k: max(0.05, (float(v) + 1.0) / 2.0) for k, v in rewards.items()}

    # ---------- high-level ----------

    def decide(
        self,
        votes: Iterable[AgentVote],
        *,
        override_weights: Optional[Mapping[str, float]] = None,
        learned_weights: Optional[Mapping[str, float]] = None,
    ) -> ConsensusDecision:
        v = tuple(votes)
        persisted = self.learned_weights()
        if learned_weights is None:
            effective_learned = persisted
        else:
            effective_learned = dict(persisted)
            for agent, weight in learned_weights.items():
                effective_learned[agent] = float(weight)

        score, weights = self.aggregate(
            v,
            learned_weights=effective_learned,
            override_weights=override_weights,
        )
        action = self.score_to_action(score)
        conf = self.confidence_from_score(score)
        return ConsensusDecision(
            action=action, score=score, confidence=conf, weights=weights, votes=v
        )


# ---------- EWS → AgentVote ----------


def ews_to_vote(
    agent_name: str, ews_result: Any, *, use_probability: bool = True
) -> AgentVote:
    """Перетворити :class:`EWSResult` у голос агента."""
    score = 0.0
    prob = getattr(ews_result, "probability", None)
    if use_probability and prob is not None:
        score = clamp(2.0 * float(prob), 0.0, 2.0) - 1.0
    elif hasattr(ews_result, "ews_score"):
        score = clamp(float(getattr(ews_result, "ews_score")), -1.0, 1.0)
    return AgentVote(
        agent=agent_name, score=score, confidence=1.0, rationale="EWS meta-signal"
    )
