"""Basal ganglia inspired decision stack orchestrating neuromodulators."""

from __future__ import annotations

from typing import Mapping, MutableMapping, NamedTuple, Optional, Sequence

from tradepulse.core.neuro.dopamine.action_gate import (
    ActionGate,
    DopamineSnapshot,
    GABASnapshot,
    NAACHSnapshot,
    SerotoninSnapshot,
)
from tradepulse.core.neuro.dopamine.dopamine_controller import DopamineController
from tradepulse.core.neuro.gaba.gaba_inhibition_gate import GABAInhibitionGate
from tradepulse.core.neuro.na_ach.neuromods import NAACHNeuromodulator
from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController


class DecisionResult(NamedTuple):
    """Immutable decision container returned by the neuromodulator stack."""

    decision: str
    score: float
    extras: Mapping[str, object]


class BasalGangliaDecisionStack:
    """Coordinate dopamine, serotonin, GABA and NA/ACh for action selection."""

    def __init__(
        self,
        *,
        dopamine_config: str = "configs/dopamine.yaml",
        serotonin_config: str = "configs/serotonin.yaml",
        gaba_config: str = "configs/gaba.yaml",
        na_ach_config: str = "configs/na_ach.yaml",
    ) -> None:
        self.dopamine = DopamineController(dopamine_config)
        self.serotonin = SerotoninController(serotonin_config)
        self.gaba = GABAInhibitionGate(gaba_config)
        self.na_ach = NAACHNeuromodulator(na_ach_config)
        self.action_gate = ActionGate(self.dopamine)

    def reset(self) -> None:
        self.dopamine.reset_state()
        self.serotonin.reset()
        self.gaba.reset()
        self.na_ach.update(0.0, 0.0)

    def select_action(
        self,
        q_values: Mapping[str, float] | Sequence[float],
        constraints: Mapping[str, float],
        gates: Optional[Mapping[str, object]] = None,
    ) -> DecisionResult:
        if isinstance(q_values, Mapping):
            action_keys = list(q_values.keys())
            logits = [float(q_values[key]) for key in action_keys]
        else:
            logits = [float(v) for v in q_values]
            action_keys = [str(idx) for idx, _ in enumerate(logits)]

        best_index = max(range(len(logits)), key=logits.__getitem__) if logits else 0
        current_value = constraints.get("value", logits[best_index] if logits else 0.0)
        next_value = constraints.get("next_value", current_value)
        reward = constraints.get("reward", 0.0)
        novelty = constraints.get("novelty", 0.0)
        momentum = constraints.get("momentum", constraints.get("motivation", 0.0))
        value_gap = max(0.0, next_value - current_value)
        reward_proxy = constraints.get("reward_proxy", max(0.0, reward))

        appetitive_state = self.dopamine.estimate_appetitive_state(
            reward_proxy,
            novelty,
            momentum,
            value_gap,
        )

        ddm_params = None
        if gates is not None:
            ddm_params = gates.get("ddm_params")

        rpe, temperature, scaled_policy, dop_extras = self.dopamine.step(
            reward=reward,
            value=current_value,
            next_value=next_value,
            appetitive_state=appetitive_state,
            policy_logits=logits,
            ddm_params=ddm_params,
            discount_gamma=constraints.get("discount_gamma"),
        )

        dopamine_snapshot = DopamineSnapshot(
            level=float(dop_extras["dopamine_level"]),
            temperature=float(temperature),
            go_threshold=float(dop_extras["go_threshold"]),
            hold_threshold=float(dop_extras["hold_threshold"]),
            no_go_threshold=float(dop_extras["no_go_threshold"]),
            release_gate_open=bool(dop_extras["release_gate_open"]),
        )

        stress = constraints.get("stress", constraints.get("drawdown", 0.0))
        drawdown = -abs(constraints.get("drawdown", 0.0))
        serotonin_state = self.serotonin.step(
            stress=float(max(0.0, stress)),
            drawdown=float(max(0.0, drawdown)),
            novelty=float(max(0.0, novelty)),
            dt=constraints.get("dt", 1.0),
        )
        serotonin_snapshot = SerotoninSnapshot(
            level=float(serotonin_state["level"]),
            hold=bool(serotonin_state["hold"] >= 0.5),
            temperature_floor=float(serotonin_state["temperature_floor"]),
        )

        gaba_state = self.gaba.update(
            sequence_intensity=constraints.get("impulse", 0.0),
            dt=constraints.get("dt", 1.0),
            rpe=rpe,
            stress=float(max(0.0, stress)),
        )
        gaba_snapshot = GABASnapshot(
            inhibition=float(gaba_state["inhibition"]),
            stdp_dw=float(gaba_state["stdp_dw"]),
        )

        na_state = self.na_ach.update(
            volatility=constraints.get("volatility", 0.0),
            novelty=float(max(0.0, novelty)),
        )
        na_snapshot = NAACHSnapshot(
            arousal=float(na_state["arousal"]),
            attention=float(na_state["attention"]),
            risk_multiplier=float(na_state["risk_multiplier"]),
            temperature_scale=float(na_state["temperature_scale"]),
        )

        gate_result = self.action_gate.evaluate(
            dopamine=dopamine_snapshot,
            serotonin=serotonin_snapshot,
            gaba=gaba_snapshot,
            na_ach=na_snapshot,
        )

        score = min(1.0, max(0.0, gate_result.score * na_state["risk_multiplier"]))
        extras: MutableMapping[str, object] = {
            "dopamine": dop_extras,
            "serotonin": serotonin_state,
            "gaba": gaba_state,
            "na_ach": na_state,
            "temperature": gate_result.temperature,
            "scaled_policy": scaled_policy,
            "chosen_action": action_keys[best_index] if action_keys else None,
        }
        if gates is not None:
            extras["input_gates"] = dict(gates)

        return DecisionResult(
            decision=gate_result.decision,
            score=score,
            extras=extras,
        )


_DEFAULT_STACK: Optional[BasalGangliaDecisionStack] = None


def _get_default_stack() -> BasalGangliaDecisionStack:
    global _DEFAULT_STACK
    if _DEFAULT_STACK is None:
        _DEFAULT_STACK = BasalGangliaDecisionStack()
    return _DEFAULT_STACK


def select_action(
    q_values: Mapping[str, float] | Sequence[float],
    constraints: Mapping[str, float],
    gates: Optional[Mapping[str, object]] = None,
) -> Mapping[str, object]:
    stack = _get_default_stack()
    result = stack.select_action(q_values, constraints, gates)
    return {
        "decision": result.decision,
        "score": result.score,
        "extras": dict(result.extras),
    }


class PolicyResult:
    """Backward compatible result container for legacy policy consumers."""

    def __init__(self, action: str, size_hint: float) -> None:
        self.action = action
        self.size_hint = size_hint


class BasalGangliaPolicy:
    """Legacy policy wrapper keeping backward compatible API."""

    def __init__(self, hold_size_hint: float = 0.2) -> None:
        self.hold_size_hint = hold_size_hint

    def decide(
        self,
        state: Mapping[str, float],
        ews_state: str,
        risk_state: str,
    ) -> tuple[str, float]:
        if ews_state == "KILL" or risk_state == "BREACH":
            return "NO_GO", 0.0
        if ews_state == "EMERGENT" and risk_state == "OK":
            synchrony = float(state.get("R", 0.5))
            size_hint = max(0.0, min(1.0, 0.5 + 0.5 * synchrony))
            return "GO", size_hint
        return "HOLD", self.hold_size_hint


__all__ = [
    "BasalGangliaDecisionStack",
    "BasalGangliaPolicy",
    "DecisionResult",
    "PolicyResult",
    "select_action",
]
