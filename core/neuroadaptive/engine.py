"""Core engine for neuroadaptive decision making."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .config import NeuroAdaptiveConfig
from .state import NeuroGateFsm
from .telemetry import neuro_event_payload
from .types import (
    ControlSignal,
    DecisionRequest,
    DecisionResult,
    LlmClient,
    NeuroGateState,
    NeuroSignals,
)


@dataclass(slots=True)
class NeuroMetrics:
    """Metrics from neuroadaptive decision processing.

    Attributes:
        confidence: Overall neuromodulator confidence score
        signal_contributions: Individual contribution from each signal
        data_quality_ok: Whether all data quality checks passed
        data_quality_issues: List of data quality issues detected
        decision_impact: Impact classification (NO_CHANGE/INCREASED/DECREASED)
    """

    confidence: float
    signal_contributions: Dict[str, float]
    data_quality_ok: bool
    data_quality_issues: Tuple[str, ...]
    decision_impact: str


class NeuroAdaptiveAgent:
    """Neuroadaptive decision agent with FSM-based gating.

    This agent processes decision requests using neuromodulator-inspired
    signals and a finite state machine for sophisticated gating control.
    It blends traditional confidence scores with neuro signals to make
    risk-aware trading decisions.
    """

    __slots__ = ("_config", "_llm", "_fsm")

    def __init__(
        self,
        llm_client: LlmClient,
        config: Optional[NeuroAdaptiveConfig] = None,
    ) -> None:
        """Initialize the neuroadaptive agent.

        Args:
            llm_client: LLM client for advanced reasoning (Protocol)
            config: Optional configuration, uses defaults if not provided
        """
        self._config = (config or NeuroAdaptiveConfig()).validated()
        self._llm = llm_client
        self._fsm = NeuroGateFsm(self._config)

    @property
    def config(self) -> NeuroAdaptiveConfig:
        """Get current configuration."""
        return self._config

    @property
    def gate_state(self) -> NeuroGateState:
        """Get current FSM gate state."""
        return self._fsm.state

    async def decide(self, req: DecisionRequest) -> DecisionResult:
        """Process a decision request through the neuroadaptive system.

        Args:
            req: Decision request with proposal and neuro signals

        Returns:
            DecisionResult with allowed status and full context
        """
        neuro = req.neuro_signals

        # Normalize and validate neuro signals
        norm_neuro, data_ok, issues = self._normalize_and_validate(neuro)

        # Calculate neuro confidence from signals
        neuro_conf, contributions = self._neuro_confidence(norm_neuro)

        # Get base confidence or use default
        base_conf = norm_neuro.prior_confidence or 0.5

        # Blend base and neuro confidence
        blended_conf = self._blend_confidence(base_conf, neuro_conf)

        # Step FSM with neuro confidence and risk
        transition = self._fsm.step(
            neuro_confidence=neuro_conf,
            risk_tag=req.risk_tag,
        )

        # Determine if action is allowed based on gate state
        allowed = self._is_allowed(transition, req.risk_tag)

        # Determine decision impact
        impact = self._impact(base_conf, blended_conf)

        # Build metrics
        metrics = NeuroMetrics(
            confidence=neuro_conf,
            signal_contributions=contributions,
            data_quality_ok=data_ok,
            data_quality_issues=tuple(issues),
            decision_impact=impact,
        )

        # Build debug telemetry
        debug = neuro_event_payload(
            gate_state=self._fsm.state,
            metrics=metrics,
            extra={
                "risk_tag": req.risk_tag,
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
        neuro: NeuroSignals,
    ) -> Tuple[NeuroSignals, bool, Tuple[str, ...]]:
        """Normalize and validate neuromodulator signals.

        Args:
            neuro: Raw neuro signals

        Returns:
            Tuple of (normalized signals, data quality OK, issues list)
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

        clipped = NeuroSignals(
            dopamine_rpe=clip("dopamine_rpe", neuro.dopamine_rpe),
            serotonin_veto=clip("serotonin_veto", neuro.serotonin_veto),
            threat_score=clip("threat_score", neuro.threat_score),
            energy_efficiency=clip("energy_efficiency", neuro.energy_efficiency),
            prior_confidence=clip("prior_confidence", neuro.prior_confidence),
        )
        ok = len(issues) == 0
        return clipped, ok, tuple(issues)

    def _neuro_confidence(
        self,
        neuro: NeuroSignals,
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate overall neuro confidence from individual signals.

        Each signal contributes according to its weight. Signals are
        transformed to [0, 1] range where applicable:
        - dopamine_rpe: [-1, 1] → [0, 1]
        - serotonin_veto: inverted (high veto = low confidence)
        - threat_score: inverted (high threat = low confidence)
        - energy_efficiency: direct mapping

        Args:
            neuro: Normalized neuro signals

        Returns:
            Tuple of (confidence score, individual contributions)
        """
        w = self._config.weights
        contrib: Dict[str, float] = {}
        num = 0.0
        den = 0.0

        if neuro.dopamine_rpe is not None:
            ww = w.get("dopamine_rpe", 0.0)
            # Map [-1, 1] to [0, 1]
            norm = (neuro.dopamine_rpe + 1.0) / 2.0
            c = norm * ww
            contrib["dopamine_rpe"] = c
            num += c
            den += ww

        if neuro.serotonin_veto is not None:
            ww = w.get("serotonin_veto", 0.0)
            # Invert: high veto = low confidence
            c = (1.0 - neuro.serotonin_veto) * ww
            contrib["serotonin_veto"] = c
            num += c
            den += ww

        if neuro.threat_score is not None:
            ww = w.get("threat_score", 0.0)
            # Invert: high threat = low confidence
            c = (1.0 - neuro.threat_score) * ww
            contrib["threat_score"] = c
            num += c
            den += ww

        if neuro.energy_efficiency is not None:
            ww = w.get("energy_efficiency", 0.0)
            c = neuro.energy_efficiency * ww
            contrib["energy_efficiency"] = c
            num += c
            den += ww

        # If no signals available, return neutral confidence
        if den == 0.0:
            return 0.5, contrib

        # Weighted average
        conf = max(0.0, min(1.0, num / den))
        return conf, contrib

    def _blend_confidence(self, base: float, neuro: float) -> float:
        """Blend base confidence with neuro confidence.

        Args:
            base: Base/prior confidence score
            neuro: Neuro-derived confidence score

        Returns:
            Blended confidence score
        """
        r = self._config.blend_ratio
        return max(0.0, min(1.0, (1.0 - r) * base + r * neuro))

    @staticmethod
    def _is_allowed(
        transition,
        risk_tag: str,
    ) -> bool:
        """Determine if action is allowed based on FSM state.

        Args:
            transition: Gate transition result
            risk_tag: Risk category

        Returns:
            True if action is allowed
        """
        state = transition.new_state

        if state == NeuroGateState.INHIBITED:
            return False

        if state == NeuroGateState.OVERRIDDEN:
            return bool(transition.control_signal == ControlSignal.OVERRIDE_ALLOW)

        if state == NeuroGateState.RELEASED:
            return True

        if state == NeuroGateState.ARMED:
            return False

        # REFLEX state: allow low/medium risk
        return risk_tag.lower() in ("low", "medium")

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
