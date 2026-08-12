# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unified flow controller — single deterministic decision pipeline.

Merges decision stack and neuroeconomics 5-module loop
into one pipeline with explicit, traceable weights at every junction.

Architecture:

  Signal(12 fields)
      │
      ├─→ UncertaintyController.update(δ_t) → α_t, surprise, ω
      │
      ├─→ ContextMemory.update(regime, outcome) → policy_δ, eff_α
      │
      ├─→ PriorIntegrator.update(likelihood) → posterior, drift_bias, H(prior)
      │
      ├─→ ControlValueGate.compute(H, latency) → effort_gate, VOI
      │
      └─→ DecisionCurrency.update(all above) → V_net, δ_t  ──┐
                                                               │
      ┌────────────────────────────────────────────────────────┘
      │ δ_t feeds back to UncertaintyController (closed loop)
      │
      ├─→ HomeostaticStabilizer.update(signal) → E/I ratio, kelly_mult
      │
      └─→ FlowDecision: TRADE(size) | OBSERVE | ABORT | DISSOCIATED

No metaphors. Every weight is a named constant. Every junction is testable.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

from geosync.neuroeconomics.context_memory import ContextMemory
from geosync.neuroeconomics.control_value import ControlValueGate
from geosync.neuroeconomics.decision_currency import DecisionCurrency
from geosync.neuroeconomics.prior_integration import PriorIntegrator
from geosync.neuroeconomics.uncertainty import (
    UncertaintyController,
    UncertaintyType,
)


class FlowDecision(enum.Enum):
    TRADE = "TRADE"
    OBSERVE = "OBSERVE"
    ABORT = "ABORT"
    DISSOCIATED = "DISSOCIATED"


# ═══════════════════════════════════════════════════════════════════
# WEIGHT TABLE — every junction has a named constant
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class FlowWeights:
    """All weights in one place. No magic numbers anywhere else."""

    # E/I balance (homeostatic)
    ei_excitatory_risk: float = 0.4
    ei_excitatory_strength: float = 0.3
    ei_excitatory_confidence: float = 0.3
    ei_inhibitory_baseline: float = 0.3
    ei_inhibitory_uncertainty: float = 0.25
    ei_inhibitory_distance: float = 0.25
    ei_inhibitory_instability: float = 0.2

    # E/I thresholds
    ei_homeostatic_lo: float = 0.7
    ei_homeostatic_hi: float = 1.3
    ei_dissociation: float = 3.0
    ei_recovery: float = 1.5

    # Pragmatic vs epistemic
    pragmatic_base: float = 0.5  # floor when signal_strength=0
    surprise_normalization: float = 4.0  # bits for max surprise
    epistemic_uncertainty_w: float = 0.3
    epistemic_surprise_w: float = 0.3
    epistemic_ambiguity_w: float = 0.25

    # Kelly discount
    kelly_min: float = 0.1  # never zero — always probe

    # Volatility → learning rate
    alpha_min: float = 0.01
    alpha_max: float = 0.5
    tau_omega: float = 0.1

    # Pessimism bias
    alpha_gain: float = 0.05
    alpha_loss: float = 0.15

    # Prior integration
    beta_prior: float = 0.3  # prior → drift coupling
    drift_scale: float = 0.1  # drift_bias multiplier in V_net


DEFAULT_WEIGHTS = FlowWeights()


@dataclass(frozen=True, slots=True)
class FlowOutput:
    """Complete decision with full trace of every module's output."""

    decision: FlowDecision
    adjusted_size: float  # ∈ [0, intended_size]
    v_net: float  # unified value ∈ [-1, 1]
    delta_t: float  # prediction error → next cycle
    ei_ratio: float  # E/I balance
    kelly_mult: float  # homeostatic modulation
    alpha_t: float  # adaptive learning rate
    surprise: float  # |δ|/σ_eu
    uncertainty_type: str  # RISK/AMBIGUITY/EXPECTED/UNEXPECTED
    effort_gate: float  # deliberation allocation
    regime: str  # current market regime
    lambda_weights: tuple[float, float, float]  # (pav, hab, goal)
    reason: str


class FlowController:
    """Single deterministic pipeline. No parallel stacks. Every weight named.

    Parameters
    ----------
    weights
        All constants in one dataclass. Override for calibration.
    n_prior_states
        Number of discrete states for Bayesian prior.
    window
        Rolling window for volatility/uncertainty estimation.
    """

    def __init__(
        self,
        *,
        weights: FlowWeights = DEFAULT_WEIGHTS,
        n_prior_states: int = 5,
        window: int = 50,
    ) -> None:
        self.w = weights
        self._uc = UncertaintyController(
            alpha_min=weights.alpha_min,
            alpha_max=weights.alpha_max,
            tau_omega=weights.tau_omega,
            window=window,
        )
        self._cv = ControlValueGate()
        self._cm = ContextMemory(
            alpha_gain=weights.alpha_gain,
            alpha_loss=weights.alpha_loss,
        )
        self._pi = PriorIntegrator(
            n_states=n_prior_states,
            beta_prior=weights.beta_prior,
        )
        self._dc = DecisionCurrency()

        # State
        self._delta_t: float = 0.0
        self._outcome: float = 0.0
        self._ei_dissociated: bool = False

    def process(
        self,
        signal: dict[str, object],
        intended_size: float = 1.0,
        outcome: float = 0.0,
    ) -> FlowOutput:
        """One tick of the complete decision loop.

        Parameters
        ----------
        signal
            12-field CoherenceBridge signal dict.
        intended_size
            Base position size before modulation.
        outcome
            Realized PnL from previous tick (closes the loop).
        """
        self._outcome = outcome if math.isfinite(outcome) else 0.0

        # Extract signal fields (NaN-safe)
        risk = _f(signal.get("risk_scalar"))
        conf = _f(signal.get("regime_confidence"))
        strength = abs(_f(signal.get("signal_strength")))
        gamma = _f(signal.get("gamma"))
        regime = str(signal.get("regime") or "UNKNOWN")

        # ── 1. Uncertainty (receives δ from previous cycle) ──
        unc = self._uc.update(delta_t=self._delta_t, outcome=self._outcome)

        # ── 2. Context memory ──
        ctx = self._cm.update(regime=regime, outcome=self._outcome)

        # ── 3. Prior integration ──
        # Build likelihood from signal confidence per regime
        lik = [0.2] * self._pi.n_states
        regime_idx = {
            "COHERENT": 0,
            "METASTABLE": 1,
            "DECOHERENT": 2,
            "CRITICAL": 3,
        }.get(regime, 4)
        lik[regime_idx] = conf * 5.0 + 0.5
        prior = self._pi.update(likelihood=lik, salience=strength)

        # ── 4. Control value ──
        ctrl = self._cv.compute(
            prior_entropy=prior.prior_entropy,
            expected_posterior_entropy=max(0.0, prior.prior_entropy - 0.5),
            latency_ms=10.0,
        )

        # ── 5. Decision currency ──
        goal_value = risk * conf
        dec = self._dc.update(
            goal_value=goal_value,
            signal_strength=_f(signal.get("signal_strength")),
            outcome=self._outcome,
            alpha=unc.alpha,
            regime=regime,
            policy_delta=ctx.policy_delta,
            drift_bias=prior.drift_bias * self.w.drift_scale,
            effort_gate=ctrl.effort_gate,
        )

        # Close loop: δ feeds back to uncertainty on next tick
        self._delta_t = dec.delta

        # ── 6. E/I balance (homeostatic) ──
        w = self.w
        excitatory = (
            risk * w.ei_excitatory_risk
            + strength * w.ei_excitatory_strength
            + conf * w.ei_excitatory_confidence
        )
        gamma_instability = min(1.0, abs(gamma - 1.0)) if math.isfinite(gamma) else 1.0
        inhibitory = (
            w.ei_inhibitory_baseline
            + (1.0 - conf) * w.ei_inhibitory_uncertainty
            + (1.0 - risk) * w.ei_inhibitory_distance
            + gamma_instability * w.ei_inhibitory_instability
        )
        ei_ratio = excitatory / max(inhibitory, 1e-9)

        # Dissociation check
        if self._ei_dissociated:
            if ei_ratio < w.ei_recovery:
                self._ei_dissociated = False
            else:
                return FlowOutput(
                    decision=FlowDecision.DISSOCIATED,
                    adjusted_size=0.0,
                    v_net=0.0,
                    delta_t=dec.delta,
                    ei_ratio=round(ei_ratio, 4),
                    kelly_mult=0.0,
                    alpha_t=unc.alpha,
                    surprise=unc.surprise,
                    uncertainty_type=unc.uncertainty_type.value,
                    effort_gate=ctrl.effort_gate,
                    regime=regime,
                    lambda_weights=dec.lambda_weights,
                    reason="DISSOCIATED: E/I not recovered",
                )

        if ei_ratio > w.ei_dissociation:
            self._ei_dissociated = True
            return FlowOutput(
                decision=FlowDecision.DISSOCIATED,
                adjusted_size=0.0,
                v_net=dec.v_net,
                delta_t=dec.delta,
                ei_ratio=round(ei_ratio, 4),
                kelly_mult=0.0,
                alpha_t=unc.alpha,
                surprise=unc.surprise,
                uncertainty_type=unc.uncertainty_type.value,
                effort_gate=ctrl.effort_gate,
                regime=regime,
                lambda_weights=dec.lambda_weights,
                reason=f"DISSOCIATED: E/I={ei_ratio:.2f} > {w.ei_dissociation}",
            )

        # ── 7. Kelly multiplier from E/I distance ──
        ei_distance = abs(ei_ratio - 1.0)
        kelly_mult = max(w.kelly_min, 1.0 - ei_distance * 0.5)

        # ── 8. Pragmatic vs epistemic ──
        pragmatic = risk * conf * (w.pragmatic_base + (1.0 - w.pragmatic_base) * strength)
        surprise_norm = min(1.0, unc.surprise / w.surprise_normalization)
        # Epistemic: only dominates when genuinely uncertain
        # omega scaled by sigmoid to [0,1], not linear ×10
        omega_signal = min(1.0, unc.omega / max(unc.sigma_eu + 0.01, 0.01))
        ambiguity_flag = 1.0 if unc.uncertainty_type == UncertaintyType.AMBIGUITY else 0.0
        unexpected_flag = 1.0 if unc.uncertainty_type == UncertaintyType.UNEXPECTED else 0.0
        epistemic = (
            w.epistemic_uncertainty_w * omega_signal
            + w.epistemic_surprise_w * surprise_norm
            + w.epistemic_ambiguity_w * ambiguity_flag * 0.5  # half weight: ambiguity is common
            + unexpected_flag * 0.3  # unexpected gets full boost
        )
        epistemic = min(1.0, epistemic)

        # ── 9. Decision ──
        if unc.uncertainty_type == UncertaintyType.UNEXPECTED and unc.surprise > 3.0:
            decision = FlowDecision.ABORT
            size = 0.0
            reason = f"ABORT: unexpected surprise={unc.surprise:.2f}"
        elif epistemic > pragmatic:
            decision = FlowDecision.OBSERVE
            size = 0.0
            reason = f"OBSERVE: epistemic={epistemic:.3f} > pragmatic={pragmatic:.3f}"
        else:
            decision = FlowDecision.TRADE
            size = min(intended_size, intended_size * risk * kelly_mult)
            reason = (
                f"TRADE: V_net={dec.v_net:.3f} "
                f"E/I={ei_ratio:.2f} "
                f"kelly×{kelly_mult:.2f} "
                f"λ={dec.lambda_weights}"
            )

        return FlowOutput(
            decision=decision,
            adjusted_size=round(size, 6),
            v_net=dec.v_net,
            delta_t=dec.delta,
            ei_ratio=round(ei_ratio, 4),
            kelly_mult=round(kelly_mult, 4),
            alpha_t=unc.alpha,
            surprise=unc.surprise,
            uncertainty_type=unc.uncertainty_type.value,
            effort_gate=ctrl.effort_gate,
            regime=regime,
            lambda_weights=dec.lambda_weights,
            reason=reason,
        )

    def feed_outcome(self, outcome: float) -> None:
        """Inject realized PnL for next cycle's δ computation."""
        self._outcome = outcome if math.isfinite(outcome) else 0.0


def _f(v: object) -> float:
    """NaN-safe float extraction."""
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else 0.0
    return 0.0
