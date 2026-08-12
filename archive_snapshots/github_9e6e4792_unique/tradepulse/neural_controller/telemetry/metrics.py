from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List

import numpy as np

from ..risk.cvar import es_alpha

log = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    t: float
    kv: Dict[str, Any]


@dataclass
class MetricsEmitter:
    """Buffer metrics for batch export while emitting structured logs."""

    buffer: List[MetricPoint] = field(default_factory=list)

    def emit(self, **kv: Any) -> None:
        payload = dict(kv)
        self.buffer.append(MetricPoint(time.time(), payload))
        log.info("neuro_metric", extra={"event": "neuro.metric", "payload": payload})

    def drain(self) -> List[MetricPoint]:
        out, self.buffer = self.buffer, []
        return out


@dataclass
class DecisionMetricsExporter:
    """Compute rolling decision quality metrics."""

    tail_window: int = 256
    _tail_rewards: Deque[float] = field(default_factory=deque, init=False)
    _decisions: int = 0
    _red_decisions: int = 0
    _red_increase: int = 0
    _alloc_scale_sum: float = 0.0
    _rpe_sum: float = 0.0
    _prediction_error_sum: float = 0.0
    _timing_sensory_ms_sum: float = 0.0
    _timing_predictive_ms_sum: float = 0.0
    _timing_model_step_ms_sum: float = 0.0
    _timing_ctrl_decide_ms_sum: float = 0.0

    def update(self, decision: Dict[str, Any]) -> Dict[str, float]:
        reward = float(decision.get("reward", 0.0))
        self._push_reward(reward)

        mode = str(decision.get("mode", "")).upper()
        action = str(decision.get("action", ""))
        alloc_scale = float(decision.get("alloc_scale", 1.0))
        rpe = float(decision.get("RPE", 0.0))
        prediction_error = float(decision.get("prediction_error", 0.0))
        timing_sensory_ms = float(decision.get("timing_sensory_ms", 0.0))
        timing_predictive_ms = float(decision.get("timing_predictive_ms", 0.0))
        timing_model_step_ms = float(decision.get("timing_model_step_ms", 0.0))
        timing_ctrl_decide_ms = float(decision.get("timing_ctrl_decide_ms", 0.0))

        self._decisions += 1
        self._alloc_scale_sum += alloc_scale
        self._rpe_sum += rpe
        self._prediction_error_sum += prediction_error
        self._timing_sensory_ms_sum += timing_sensory_ms
        self._timing_predictive_ms_sum += timing_predictive_ms
        self._timing_model_step_ms_sum += timing_model_step_ms
        self._timing_ctrl_decide_ms_sum += timing_ctrl_decide_ms

        if mode == "RED":
            self._red_decisions += 1
            if action == "increase_risk":
                self._red_increase += 1

        metrics = {
            "tail_ES95": self._tail_es(),
            "prop_RED": self._ratio(self._red_decisions, self._decisions),
            "prop_increase_risk_in_RED": self._ratio(
                self._red_increase, max(1, self._red_decisions)
            ),
            "avg_alloc_scale": self._ratio(self._alloc_scale_sum, self._decisions),
            "rpe_mean": self._ratio(self._rpe_sum, self._decisions),
            "prediction_error": self._ratio(
                self._prediction_error_sum, self._decisions
            ),
            "timing_sensory_ms": self._ratio(
                self._timing_sensory_ms_sum, self._decisions
            ),
            "timing_predictive_ms": self._ratio(
                self._timing_predictive_ms_sum, self._decisions
            ),
            "timing_model_step_ms": self._ratio(
                self._timing_model_step_ms_sum, self._decisions
            ),
            "timing_ctrl_decide_ms": self._ratio(
                self._timing_ctrl_decide_ms_sum, self._decisions
            ),
        }
        return metrics

    def bulk_update(self, decisions: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        metrics: Dict[str, float] = {}
        for decision in decisions:
            metrics = self.update(decision)
        return metrics

    def _push_reward(self, reward: float) -> None:
        self._tail_rewards.append(float(reward))
        if len(self._tail_rewards) > self.tail_window:
            self._tail_rewards.popleft()

    def _tail_es(self) -> float:
        if not self._tail_rewards:
            return 0.0
        return es_alpha(np.asarray(self._tail_rewards, dtype=float), 0.95)

    @staticmethod
    def _ratio(num: float, denom: int | float) -> float:
        if denom == 0:
            return 0.0
        return float(num) / float(denom)
