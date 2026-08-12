"""Unified neuroeconomic decision engine for CoherenceBridge.

Pipeline per signal:
  1. NHS homeostatic balance (E/I ratio → kelly multiplier)
  2. Uncertainty decomposition (aleatoric + epistemic + ambiguity)
  3. Regime transition memory (surprise + pattern detection)
  4. Active Inference policy (TRADE / OBSERVE / ABORT)
  5. DecisionOutput with full reasoning

This is what Askar plugs into OTP:
  engine.process(signal, intended_size) → DecisionOutput
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from geosync.neuroeconomics.epistemic_action import (
    DecisionOutput,
    EpistemicActionModule,
    EpistemicDecision,
)
from geosync.neuroeconomics.homeostatic_stabilizer import (
    HomeostaticState,
    NeuroHomeostaticStabilizer,
)
from geosync.neuroeconomics.regime_memory import RegimeMemory
from geosync.neuroeconomics.uncertainty import UncertaintyEstimator

if TYPE_CHECKING:
    from coherence_bridge.engine_interface import SignalEngine


class GeoSyncDecisionEngine:
    """Unified decision engine composing all neuroeconomic modules.

    Composition:
      NHS (E/I balance) → Uncertainty → RegimeMemory → EpistemicAction

    NHS modulates kelly_fraction BEFORE epistemic decision.
    If NHS enters DISSOCIATED state → force ABORT regardless of epistemic.
    """

    def __init__(
        self,
        engine: SignalEngine,
        *,
        uncertainty_window: int = 100,
        abort_threshold: float = 2.0,
        ei_dissociation: float = 3.0,
    ) -> None:
        self._engine = engine
        self._nhs = NeuroHomeostaticStabilizer(
            dissociation_threshold=ei_dissociation,
        )
        self._uncertainty = UncertaintyEstimator(window=uncertainty_window)
        self._memory = RegimeMemory(prior_count=1.0)
        self._epistemic = EpistemicActionModule(
            uncertainty_estimator=self._uncertainty,
            regime_memory=self._memory,
            abort_threshold=abort_threshold,
        )
        from geosync.neuroeconomics.ergodicity_correction import (
            ErgodicityCorrection,
        )

        self._ergodicity = ErgodicityCorrection()
        self._last_nhs: HomeostaticState | None = None

    def process(
        self,
        signal: dict[str, object],
        intended_size: float = 1.0,
    ) -> DecisionOutput:
        """Full neuroeconomic decision pipeline.

        1. NHS computes E/I balance → kelly_multiplier
        2. If DISSOCIATED → force ABORT (protective shutdown)
        3. Otherwise → epistemic decides TRADE/OBSERVE/ABORT
        4. If TRADE → scale by NHS kelly_multiplier
        """
        # Step 1: Homeostatic balance
        nhs_state = self._nhs.update(signal)
        self._last_nhs = nhs_state

        # Step 1b: Ergodicity correction (Peters SDE)
        returns_window = signal.get("returns_window")
        if returns_window is not None:
            import numpy as np

            erg = self._ergodicity.update(np.asarray(returns_window))
            if not erg.is_ergodic:
                intended_size = intended_size * erg.pragmatic_corrected

        # Step 2: Dissociative shield override
        if nhs_state.regime == "DISSOCIATED":
            return DecisionOutput(
                decision=EpistemicDecision.ABORT,
                pragmatic_value=0.0,
                epistemic_value=1.0,
                ambiguity_index=0.0,
                regime_surprise=0.0,
                reason=(
                    f"NHS DISSOCIATED: E/I={nhs_state.ei_ratio:.2f}"
                    f" entropy={nhs_state.entropy:.2f}"
                    " — protective shutdown"
                ),
                adjusted_size=0.0,
            )

        # Step 3: Epistemic decision
        epistemic_out = self._epistemic.decide(signal, intended_size)

        # Step 4: Modulate TRADE size by NHS kelly_multiplier
        if epistemic_out.decision == EpistemicDecision.TRADE:
            modulated_size = epistemic_out.adjusted_size * nhs_state.kelly_multiplier
            return DecisionOutput(
                decision=epistemic_out.decision,
                pragmatic_value=epistemic_out.pragmatic_value,
                epistemic_value=epistemic_out.epistemic_value,
                ambiguity_index=epistemic_out.ambiguity_index,
                regime_surprise=epistemic_out.regime_surprise,
                reason=(
                    f"{epistemic_out.reason}"
                    f" | NHS {nhs_state.regime}"
                    f" E/I={nhs_state.ei_ratio:.2f}"
                    f" kelly×{nhs_state.kelly_multiplier:.2f}"
                ),
                adjusted_size=round(modulated_size, 6),
            )

        return epistemic_out

    def process_live(
        self,
        instrument: str,
        intended_size: float = 1.0,
    ) -> DecisionOutput | None:
        """Fetch live signal from engine and process."""
        sig = self._engine.get_signal(instrument)
        if sig is None:
            return None
        return self.process(sig, intended_size)

    def get_state_summary(self, instrument: str) -> dict[str, Any]:
        """State summary for Grafana dashboard and RF feature export."""
        nhs = self._last_nhs
        return {
            "expected_next_regime": self._memory.get_expected_next(instrument),
            "uncertainty_window": getattr(self._uncertainty, "_delta_acc", None)
            and self._uncertainty._delta_acc._maxn
            or 50,
            "nhs_regime": nhs.regime if nhs else "UNKNOWN",
            "nhs_ei_ratio": nhs.ei_ratio if nhs else 0.0,
            "nhs_kelly_mult": nhs.kelly_multiplier if nhs else 0.0,
            "nhs_entropy": nhs.entropy if nhs else 0.0,
            "nhs_dissociated": self._nhs.is_dissociated,
        }
