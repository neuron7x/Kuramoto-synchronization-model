"""Active Inference policy selection for trading decisions.

Implements Karl Friston's Expected Free Energy decomposition:

  Expected Free Energy = Pragmatic Value + Epistemic Value
                       = "how much we earn" + "how much we learn"

When epistemic > pragmatic → OBSERVE (don't trade, gather information)
When pragmatic > epistemic → TRADE (execute with risk-adjusted size)
When ambiguity > threshold → ABORT (uncertainty about uncertainty too high)

This is the module Askar's EKF cannot replicate — it decides WHEN not to
trade, which is the most valuable signal in quantitative finance.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from geosync.neuroeconomics.regime_memory import RegimeMemory
from geosync.neuroeconomics.uncertainty import UncertaintyEstimator


class EpistemicDecision(enum.Enum):
    """Three-valued decision output."""

    TRADE = "TRADE"
    OBSERVE = "OBSERVE"
    ABORT = "ABORT"


@dataclass(frozen=True, slots=True)
class DecisionOutput:
    """Complete decision with reasoning."""

    decision: EpistemicDecision
    pragmatic_value: float  # expected PnL proxy [0, 1]
    epistemic_value: float  # information gain proxy [0, 1]
    ambiguity_index: float  # second-order uncertainty
    regime_surprise: float  # transition anomaly score
    reason: str
    adjusted_size: float  # 0.0 if OBSERVE/ABORT


class EpistemicActionModule:
    """Active Inference decision layer.

    Parameters
    ----------
    uncertainty_estimator
        Computes aleatoric/epistemic/ambiguity decomposition.
    regime_memory
        Tracks transition probabilities and detects anomalies.
    abort_threshold
        Ambiguity index above which ABORT is forced.
    """

    ABORT_THRESHOLD = 2.0

    def __init__(
        self,
        uncertainty_estimator: UncertaintyEstimator,
        regime_memory: RegimeMemory,
        abort_threshold: float = 2.0,
    ) -> None:
        self._uncertainty = uncertainty_estimator
        self._memory = regime_memory
        self.ABORT_THRESHOLD = abort_threshold

    def decide(
        self,
        signal: dict[str, object],
        intended_size: float = 1.0,
    ) -> DecisionOutput:
        """Full Active Inference decision pipeline.

        1. Decompose uncertainty (aleatoric + epistemic + ambiguity)
        2. Observe regime transition (surprise score)
        3. Compute pragmatic vs epistemic value
        4. Select policy: TRADE / OBSERVE / ABORT
        """
        instrument = str(signal.get("instrument", ""))
        regime = str(signal.get("regime", "UNKNOWN"))

        # 1. Uncertainty
        unc = self._uncertainty.update(signal)

        # 2. Regime memory
        trans = self._memory.observe(instrument, regime)

        # 3. Pragmatic value
        # Base = risk_scalar × confidence (edge quality)
        # Boost from directional signal strength (optional)
        risk_scalar = _to_float(signal.get("risk_scalar"))
        confidence = _to_float(signal.get("regime_confidence"))
        strength = abs(_to_float(signal.get("signal_strength")))
        pragmatic = risk_scalar * confidence * (0.5 + 0.5 * strength)

        # 4. Epistemic value
        # Scales with uncertainty and surprise, normalized to [0, 1]
        # Key: only exceeds pragmatic when model genuinely doesn't know
        surprise_norm = min(1.0, trans.surprise / 4.0)  # surprise in bits, 4 bits = max
        epistemic = (
            unc.epistemic * 0.4
            + surprise_norm * 0.3
            + max(0.0, unc.ambiguity_index - 1.0) * 0.3  # only penalize above 1.0
        )
        epistemic = min(1.0, epistemic)

        # 5. Decision
        # ABORT: ambiguity too high OR unexpected surprise spike
        is_unexpected = getattr(unc, "uncertainty_type", None)
        unexpected_abort = (
            hasattr(is_unexpected, "value")
            and is_unexpected.value == "UNEXPECTED"
            and unc.surprise > 3.0
        )
        if unc.ambiguity_index > self.ABORT_THRESHOLD or unexpected_abort:
            return DecisionOutput(
                decision=EpistemicDecision.ABORT,
                pragmatic_value=round(pragmatic, 4),
                epistemic_value=round(epistemic, 4),
                ambiguity_index=round(unc.ambiguity_index, 4),
                regime_surprise=round(trans.surprise, 4),
                reason=(
                    f"Ambiguity {unc.ambiguity_index:.2f} > {self.ABORT_THRESHOLD}"
                    " — uncertainty about uncertainty too high"
                ),
                adjusted_size=0.0,
            )

        if epistemic > pragmatic:
            return DecisionOutput(
                decision=EpistemicDecision.OBSERVE,
                pragmatic_value=round(pragmatic, 4),
                epistemic_value=round(epistemic, 4),
                ambiguity_index=round(unc.ambiguity_index, 4),
                regime_surprise=round(trans.surprise, 4),
                reason=(
                    f"Epistemic {epistemic:.3f} > pragmatic {pragmatic:.3f}"
                    " — gather information, don't trade"
                ),
                adjusted_size=0.0,
            )

        # TRADE: scale by kelly discount from uncertainty
        kelly_mult = self._uncertainty.kelly_discount(unc)
        adjusted = min(intended_size, intended_size * risk_scalar * kelly_mult)

        return DecisionOutput(
            decision=EpistemicDecision.TRADE,
            pragmatic_value=round(pragmatic, 4),
            epistemic_value=round(epistemic, 4),
            ambiguity_index=round(unc.ambiguity_index, 4),
            regime_surprise=round(trans.surprise, 4),
            reason=(
                f"Pragmatic {pragmatic:.3f} > epistemic {epistemic:.3f}"
                f" — trade at {kelly_mult:.0%} Kelly"
            ),
            adjusted_size=round(adjusted, 6),
        )


def _to_float(v: object) -> float:
    """Safe float — NaN/Inf → 0.0 (fail-closed)."""
    if isinstance(v, (int, float)):
        import math as _m

        f = float(v)
        return f if _m.isfinite(f) else 0.0
    return 0.0
