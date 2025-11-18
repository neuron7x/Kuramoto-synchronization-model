"""Core engine for heuristic gate decision making."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .config import HeuristicGateConfig
from .exceptions import InvalidSignalsError
from .fsm import HeuristicGateFsm
from .telemetry import gate_event_payload
from .types import (
    ControlSignal,
    DecisionRequest,
    DecisionResult,
    GateState,
    HeuristicSignals,
    RiskLevel,
)


@dataclass(slots=True)
class GateMetrics:
    """Metrics from heuristic gate decision processing.

    Attributes:
        confidence: Overall gate confidence score
        signal_contributions: Normalized contribution from each signal
        data_quality_ok: Whether all data quality checks passed
        data_quality_issues: List of data quality issues detected
        decision_impact: Impact classification (NO_CHANGE/INCREASED/DECREASED)
    """

    confidence: float
    signal_contributions: Dict[str, float]
    data_quality_ok: bool
    data_quality_issues: Tuple[str, ...]
    decision_impact: str


class HeuristicDecisionGate:
    """Heuristic decision gate with strict validation and FSM-based control.

    This gate processes decision requests using heuristic signals and
    a table-driven finite state machine. Unlike the neuroadaptive system,
    this implementation raises exceptions on validation failures.
    """

    __slots__ = ("_config", "_fsm")

    def __init__(
        self,
        config: Optional[HeuristicGateConfig] = None,
    ) -> None:
        """Initialize the heuristic decision gate.

        Args:
            config: Optional configuration, uses defaults if not provided
        """
        self._config = (config or HeuristicGateConfig.default()).validated()
        self._fsm = HeuristicGateFsm(self._config)

    @property
    def config(self) -> HeuristicGateConfig:
        """Get current configuration."""
        return self._config

    @property
    def gate_state(self) -> GateState:
        """Get current FSM gate state."""
        return self._fsm.state

    def decide(self, req: DecisionRequest) -> DecisionResult:
        """Process a decision request through the heuristic gate.

        Args:
            req: Decision request with proposal and heuristic signals

        Returns:
            DecisionResult with allowed status and full context

        Raises:
            InvalidSignalsError: If signals fail validation
        """
        signals = req.signals

        # Normalize and validate signals (raises on failure)
        norm_signals, ok, issues = self._normalize_and_validate(signals)
        if not ok:
            raise InvalidSignalsError(
                "invalid heuristic signals",
                issues=issues,
                data=signals.as_dict(),
            )

        # Calculate gate confidence from signals
        gate_conf, contributions = self._gate_confidence(norm_signals)

        # Get base confidence or use default
        base_conf = norm_signals.prior_confidence or 0.5

        # Blend base and gate confidence
        blended_conf = self._blend_confidence(base_conf, gate_conf)

        # Determine control signal based on confidence and risk
        control = self._control_signal(gate_conf, req.risk_level)
        reason = self._control_reason(gate_conf, req.risk_level, control)

        # Apply control signal to FSM
        transition = self._fsm.apply(control, reason)

        # Determine if action is allowed based on gate state
        allowed = self._is_allowed(
            transition.new_state, transition.control_signal, req.risk_level
        )

        # Determine decision impact
        impact = self._impact(base_conf, blended_conf)

        # Build metrics with normalized contributions
        metrics = GateMetrics(
            confidence=gate_conf,
            signal_contributions=self._normalize_contributions(contributions),
            data_quality_ok=True,
            data_quality_issues=(),
            decision_impact=impact,
        )

        # Build debug telemetry
        debug = gate_event_payload(
            gate_state=self._fsm.state,
            metrics=metrics,
            extra={
                "risk_level": req.risk_level.name,
                "base_confidence": base_conf,
                "blended_confidence": blended_conf,
            },
        )

        return DecisionResult(
            allowed=allowed,
            gate_state=self._fsm.state,
            blended_confidence=blended_conf,
            control_signal=transition.control_signal,
            reason=transition.reason,
            debug=debug,
        )

    def _normalize_and_validate(
        self,
        signals: HeuristicSignals,
    ) -> Tuple[HeuristicSignals, bool, Tuple[str, ...]]:
        """Normalize and validate heuristic signals.

        Args:
            signals: Raw heuristic signals

        Returns:
            Tuple of (normalized signals, validation OK, issues list)
        """
        cfg = self._config
        issues = []

        def clip(name: str, val: float | None) -> float | None:
            """Clip signal value to configured range."""
            if val is None:
                return None
            low, high = cfg.ranges[name]
            if val < low or val > high:
                issues.append(f"{name} out of range [{low},{high}], got {val}")
            return max(low, min(high, val))

        clipped = HeuristicSignals(
            reward_error=clip("reward_error", signals.reward_error),
            inhibition_strength=clip(
                "inhibition_strength", signals.inhibition_strength
            ),
            risk_score=clip("risk_score", signals.risk_score),
            energy_efficiency=clip("energy_efficiency", signals.energy_efficiency),
            prior_confidence=clip("prior_confidence", signals.prior_confidence),
        )
        ok = len(issues) == 0
        return clipped, ok, tuple(issues)

    def _gate_confidence(
        self,
        signals: HeuristicSignals,
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate overall gate confidence from individual signals.

        Each signal contributes according to its weight. Signals are
        transformed to [0, 1] range where applicable:
        - reward_error: [-1, 1] → [0, 1]
        - inhibition_strength: inverted (high inhibition = low confidence)
        - risk_score: inverted (high risk = low confidence)
        - energy_efficiency: direct mapping

        Args:
            signals: Normalized heuristic signals

        Returns:
            Tuple of (confidence score, raw contributions)
        """
        w = self._config.weights
        num = 0.0
        den = 0.0
        contrib: Dict[str, float] = {}

        if signals.reward_error is not None:
            ww = w.get("reward_error", 0.0)
            # Map [-1, 1] to [0, 1]
            norm = (signals.reward_error + 1.0) / 2.0
            c = norm * ww
            contrib["reward_error"] = c
            num += c
            den += ww

        if signals.inhibition_strength is not None:
            ww = w.get("inhibition_strength", 0.0)
            # Invert: high inhibition = low confidence
            c = (1.0 - signals.inhibition_strength) * ww
            contrib["inhibition_strength"] = c
            num += c
            den += ww

        if signals.risk_score is not None:
            ww = w.get("risk_score", 0.0)
            # Invert: high risk = low confidence
            c = (1.0 - signals.risk_score) * ww
            contrib["risk_score"] = c
            num += c
            den += ww

        if signals.energy_efficiency is not None:
            ww = w.get("energy_efficiency", 0.0)
            c = signals.energy_efficiency * ww
            contrib["energy_efficiency"] = c
            num += c
            den += ww

        # If no signals available, return neutral confidence
        if den == 0.0:
            return 0.5, contrib

        # Weighted average
        conf = max(0.0, min(1.0, num / den))
        return conf, contrib

    def _normalize_contributions(
        self, contributions: Dict[str, float]
    ) -> Dict[str, float]:
        """Normalize contributions to sum to 1.0.

        Args:
            contributions: Raw signal contributions

        Returns:
            Normalized contributions that sum to 1.0
        """
        total = sum(contributions.values())
        if total <= 0.0:
            return {k: 0.0 for k in contributions}
        return {k: v / total for k, v in contributions.items()}

    def _blend_confidence(self, base: float, gate: float) -> float:
        """Blend base confidence with gate confidence.

        Args:
            base: Base/prior confidence score
            gate: Gate-derived confidence score

        Returns:
            Blended confidence score
        """
        r = self._config.blend_ratio
        return max(0.0, min(1.0, (1.0 - r) * base + r * gate))

    def _control_signal(
        self,
        gate_confidence: float,
        risk_level: RiskLevel,
    ) -> ControlSignal:
        """Determine control signal based on confidence and risk.

        Args:
            gate_confidence: Gate confidence score
            risk_level: Risk level of the decision

        Returns:
            Appropriate control signal
        """
        t = self._config.gate_thresholds
        c = max(0.0, min(1.0, gate_confidence))

        # Hard block: confidence too low
        if c <= t["hard_block"]:
            return ControlSignal.INHIBIT

        # Soft block: confidence low
        if c <= t["soft_block"]:
            return ControlSignal.INHIBIT

        # Hard allow: high confidence
        if c >= t["hard_allow"]:
            if risk_level is RiskLevel.CRITICAL:
                return ControlSignal.ARM
            return ControlSignal.RELEASE

        # Soft allow: moderate confidence
        if c >= t["soft_allow"]:
            if risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM):
                return ControlSignal.RELEASE
            return ControlSignal.ARM

        # Middle band
        return ControlSignal.ARM

    @staticmethod
    def _control_reason(
        gate_confidence: float,
        risk_level: RiskLevel,
        signal: ControlSignal,
    ) -> str:
        """Generate human-readable reason for control signal.

        Args:
            gate_confidence: Gate confidence score
            risk_level: Risk level
            signal: Control signal

        Returns:
            Descriptive reason string
        """
        return (
            f"gate_confidence={gate_confidence:.2f}, "
            f"risk_level={risk_level.name}, "
            f"control_signal={signal.name}"
        )

    @staticmethod
    def _is_allowed(
        new_state: GateState,
        control_signal: ControlSignal | None,
        risk_level: RiskLevel,
    ) -> bool:
        """Determine if action is allowed based on FSM state.

        Args:
            new_state: New FSM state after transition
            control_signal: Control signal that caused transition
            risk_level: Risk level of decision

        Returns:
            True if action is allowed
        """
        if new_state is GateState.INHIBITED:
            return False

        if new_state is GateState.OVERRIDDEN:
            return control_signal is ControlSignal.OVERRIDE_ALLOW

        if new_state is GateState.RELEASED:
            return True

        if new_state is GateState.ARMED:
            return False

        # REFLEX state: allow low/medium risk
        return risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)

    @staticmethod
    def _impact(base: float, final: float, eps: float = 1e-3) -> str:
        """Classify decision impact on confidence.

        Args:
            base: Base confidence
            final: Final blended confidence
            eps: Epsilon threshold for change detection

        Returns:
            Impact classification string
        """
        if abs(base - final) < eps:
            return "NO_CHANGE"
        if final > base:
            return "INCREASED"
        return "DECREASED"
