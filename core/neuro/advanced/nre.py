"""Neuroplastic reinforcement engine."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict

import numpy as np

from .config import NeuroAdvancedConfig
from .types import TradeOutcome, TradeResult


class NeuroplasticReinforcementEngine:
    """Applies LTP/LTD style reinforcement to strategy weights."""

    def __init__(self, config: NeuroAdvancedConfig):
        self._cfg = config
        self._ltp = config.nre.ltp_rate
        self._ltd = config.nre.ltd_rate
        self._decay = config.nre.weight_decay
        self._consolidation_threshold = config.nre.consolidation_threshold

        self._weights: Dict[str, float] = defaultdict(lambda: 0.5)
        self._usage: Dict[str, int] = defaultdict(int)
        self._success_rate: Dict[str, float] = defaultdict(lambda: 0.5)
        self._episodes: deque[Dict[str, Any]] = deque(maxlen=config.nre.max_memory_size)
        self._consolidated: list[Dict[str, Any]] = []
        self._context_associations: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

    def reinforce(
        self, strategy_id: str, outcome: TradeResult, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        previous_weight = self._weights[strategy_id]
        self._usage[strategy_id] += 1

        reinforcement = self._reinforcement_signal(outcome, context)
        if reinforcement > 0:
            delta = self._ltp * reinforcement * (1.0 - previous_weight)
            learning_type = "LTP"
        else:
            delta = self._ltd * reinforcement * previous_weight
            learning_type = "LTD"

        new_weight = float(np.clip((previous_weight + delta) * self._decay, 0.0, 1.0))
        self._weights[strategy_id] = new_weight

        self._update_success_rate(strategy_id, outcome)
        episode = {
            "timestamp": datetime.now(),
            "strategy_id": strategy_id,
            "reinforcement": float(reinforcement),
            "learning_type": learning_type,
            "weight_before": float(previous_weight),
            "weight_after": float(new_weight),
            "outcome": outcome.to_dict(),
            "context": dict(context),
        }
        self._episodes.append(episode)

        if self._should_consolidate(strategy_id):
            self._consolidate(strategy_id)

        self._update_context_association(strategy_id, context, reinforcement)

        return {
            "strategy_id": strategy_id,
            "old_weight": float(previous_weight),
            "new_weight": float(new_weight),
            "weight_delta": float(new_weight - previous_weight),
            "reinforcement": float(reinforcement),
            "learning_type": learning_type,
            "usage_count": int(self._usage[strategy_id]),
            "success_rate": float(self._success_rate[strategy_id]),
        }

    def context_preference(self, strategy_id: str, context: Dict[str, Any]) -> float:
        regime = context.get("regime", "normal")
        volatility = float(context.get("volatility", 0.0))
        volatility_bucket = (
            "low" if volatility < 0.2 else ("med" if volatility < 0.5 else "high")
        )
        key = f"{regime}_{volatility_bucket}"
        return float(self._context_associations[strategy_id].get(key, 0.0))

    def get_strategy_weight(self, strategy_id: str) -> float:
        return float(self._weights.get(strategy_id, 0.5))

    def state(self) -> Dict[str, Any]:
        weights = list(self._weights.values())
        avg_weight = float(np.mean(weights)) if weights else 0.5
        top_strategies = sorted(
            self._weights.items(), key=lambda item: item[1], reverse=True
        )[:5]
        return {
            "num_strategies": len(self._weights),
            "avg_strategy_weight": avg_weight,
            "top_strategies": [
                (name, float(weight)) for name, weight in top_strategies
            ],
            "strategy_weights": dict(self._weights),
            "success_rates": dict(self._success_rate),
            "episodic_memory_size": len(self._episodes),
            "consolidated_memories": len(self._consolidated),
        }

    def _reinforcement_signal(
        self, outcome: TradeResult, context: Dict[str, Any]
    ) -> float:
        base = float(outcome.pnl_percentage)
        signal_strength = 0.5 + float(outcome.signal_strength) * 0.5
        context_fit = float(context.get("context_fit", 1.0))
        return float(np.tanh(base * signal_strength * context_fit * 2.0))

    def _update_success_rate(self, strategy_id: str, outcome: TradeResult) -> None:
        current = self._success_rate[strategy_id]
        if outcome.outcome == TradeOutcome.WIN:
            target = 1.0
        elif outcome.outcome == TradeOutcome.LOSS:
            target = 0.0
        else:
            target = 0.5
        alpha = 0.1
        self._success_rate[strategy_id] = current * (1 - alpha) + target * alpha

    def _should_consolidate(self, strategy_id: str) -> bool:
        return (
            self._weights[strategy_id] > self._consolidation_threshold
            and self._usage[strategy_id] >= 20
            and self._usage[strategy_id] % 20 == 0
        )

    def _consolidate(self, strategy_id: str) -> None:
        related = [
            episode
            for episode in self._episodes
            if episode["strategy_id"] == strategy_id
        ]
        if not related:
            return
        self._consolidated.append(
            {
                "strategy_id": strategy_id,
                "time": datetime.now(),
                "num_episodes": len(related),
                "avg_weight": float(
                    np.mean([episode["weight_after"] for episode in related])
                ),
                "success_rate": float(self._success_rate[strategy_id]),
                "usage_count": int(self._usage[strategy_id]),
            }
        )

    def _update_context_association(
        self, strategy_id: str, context: Dict[str, Any], reinforcement: float
    ) -> None:
        regime = context.get("regime", "normal")
        volatility = float(context.get("volatility", 0.0))
        volatility_bucket = (
            "low" if volatility < 0.2 else ("med" if volatility < 0.5 else "high")
        )
        key = f"{regime}_{volatility_bucket}"
        alpha = 0.05
        current = self._context_associations[strategy_id][key]
        self._context_associations[strategy_id][key] = (
            current * (1 - alpha) + float(reinforcement) * alpha
        )
