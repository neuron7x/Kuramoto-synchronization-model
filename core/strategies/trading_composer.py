# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unified trading decision composer — end-to-end closure of the crypto pipeline.

This module is the load-bearing integration point for the three crypto
subsystems that landed in PR #199 and PR #200:

1. **Flow metrics** (``core/indicators/flow_metrics.py``)
     — QILM: microstructure liquidity quality per bar
     — FMN:  bounded flow-momentum oscillator

2. **π-system phase-entry gate** (``core/indicators/phase_entry_gate.py``)
     — Composes Kuramoto R, ΔH entropy, κ̄ Ricci, Hurst H into a
       deterministic ``LONG | SHORT | NEUTRAL`` decision.

3. **BTC Field Order v3.2 rule engine** (``core/strategies/btc_intel.py``)
     — Priority-ordered IF-THEN rules over a strict market snapshot,
       including a distinct ``AVOID`` state for known trap geometries.

The composer fuses their outputs into **one** ``CompositeDecision`` via
an explicit, documented conflict-resolution policy. Each subsystem
remains independently testable; this module is pure glue with zero
physics of its own.

Conflict resolution
-------------------

Priority is intentional and fail-closed. The order is:

    0. Any input NaN / Inf          → NEUTRAL + refusal_reason
    1. BTC rule R02 (AVOID trap)    → AVOID, regardless of the rest
    2. Any other BTC rule           → that rule's signal
    3. PhaseEntryGate (LONG/SHORT)  → that signal, if it matches the
                                      flow-metric sign; otherwise NEUTRAL
                                      with ``conflict_detected=True``
    4. Flow metrics only (QILM+FMN) → LONG/SHORT if both agree in sign
                                      above ``flow_min_magnitude``,
                                      otherwise NEUTRAL
    5. Nothing fires                → NEUTRAL

Rationale
---------
* The BTC rule engine's ``AVOID`` is non-negotiable — the author's
  original spec treats trap geometries as strict refusals. They win
  even over a simultaneously-firing LONG from the π-gate.
* A BTC-rule directional signal (R01/R03/R04/R05/R06/R07) expresses a
  whole-market regime call and therefore outranks the cross-sectional
  π-gate, which only sees synchronisation/curvature.
* When the π-gate fires and the flow metrics are neutral or
  contradictory, we **downgrade to NEUTRAL** — the physics layer
  without microstructure confirmation is not enough to commit capital
  on live crypto. This is the hard-won lesson from the Askar cycle
  (PRs #188–#198): topology-only signals do not clear institutional
  gates.
* Pure flow-only signals fire only when BOTH QILM and FMN agree in
  sign AND their magnitudes exceed ``flow_min_magnitude``. Either
  alone is a weak prior.

Honesty contract
----------------
No composite decision is ever emitted on partial data. A NaN in any
field of the ``TradingSnapshot`` forces NEUTRAL with an explicit
refusal reason — matching ``agent/invariants.INV_004_nan_policy``
and the ``SYSTEM_ARTIFACT_v9.0`` fail-closed pattern shipped in PR
#198.

Determinism
-----------
``compose_decision`` is a pure function: same inputs → same output,
no global state, thread-safe, ``mypy --strict`` clean.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from core.indicators.phase_entry_gate import (
    DEFAULT_PHASE_ENTRY_CONFIG,
    GateReading,
    PhaseEntryGate,
    PhaseEntryGateConfig,
    Signal,
)
from core.strategies.btc_intel import (
    DEFAULT_BTC_RULE_CONFIG,
    BTCMarketSnapshot,
    BTCRule,
    BTCRuleConfig,
    BTCRuleResult,
    BTCSignal,
    evaluate_btc_rules,
)

__all__ = [
    "CompositeSignal",
    "TradingSnapshot",
    "TradingComposerConfig",
    "CompositeDecision",
    "TradingComposer",
    "compose_decision",
    "DEFAULT_TRADING_COMPOSER_CONFIG",
]


class CompositeSignal(Enum):
    """Final four-state decision after all layers have been consulted."""

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    AVOID = "avoid"


@dataclass(frozen=True, slots=True)
class TradingSnapshot:
    """Full input bundle for the unified decision path.

    Field groups:

    * ``r_kuramoto``, ``delta_h``, ``kappa_mean``, ``hurst``
        — the four π-system primitives, already reduced to scalars.
    * ``qilm_latest``, ``fmn_latest``
        — the most recent valid reading from each flow metric.
    * ``btc_snapshot``
        — the strict BTC market snapshot for the §7 rule engine.

    Every scalar must be finite; NaN forces a refusal. The BTC
    snapshot has its own NaN guard and is checked independently.
    """

    r_kuramoto: float
    delta_h: float
    kappa_mean: float
    hurst: float
    qilm_latest: float
    fmn_latest: float
    btc_snapshot: BTCMarketSnapshot

    def has_nan(self) -> bool:
        scalars = (
            self.r_kuramoto,
            self.delta_h,
            self.kappa_mean,
            self.hurst,
            self.qilm_latest,
            self.fmn_latest,
        )
        if any(not math.isfinite(v) for v in scalars):
            return True
        return self.btc_snapshot.has_nan()


@dataclass(frozen=True, slots=True)
class TradingComposerConfig:
    """Thresholds and sub-configs for the composer.

    Both sub-configs can be overridden independently. The composer
    owns its own knobs too — minimum flow magnitude for the fallback
    branch and the Kuramoto gate config.
    """

    phase_gate_config: PhaseEntryGateConfig = field(
        default_factory=lambda: DEFAULT_PHASE_ENTRY_CONFIG,
    )
    btc_rule_config: BTCRuleConfig = field(
        default_factory=lambda: DEFAULT_BTC_RULE_CONFIG,
    )
    #: Minimum |QILM| and |FMN| required for a flow-only LONG/SHORT.
    flow_min_magnitude: float = 0.20

    def __post_init__(self) -> None:
        if self.flow_min_magnitude <= 0.0:
            raise ValueError(
                f"flow_min_magnitude must be > 0, got {self.flow_min_magnitude}",
            )


DEFAULT_TRADING_COMPOSER_CONFIG: Final[TradingComposerConfig] = TradingComposerConfig()


@dataclass(frozen=True, slots=True)
class CompositeDecision:
    """End-to-end composite decision with full provenance.

    Attributes
    ----------
    signal
        The final four-state decision.
    source_layer
        Which subsystem produced the winning signal — one of
        ``"btc_rules" | "phase_gate" | "flow_metrics" | "neutral"``.
    btc_result
        The full BTC rule-engine result (may be ``NEUTRAL``).
    phase_reading
        The π-gate reading (may be ``NEUTRAL``).
    flow_sign
        The sign obtained by combining ``QILM`` and ``FMN``: +1 long,
        −1 short, 0 neutral/contradictory.
    conflict_detected
        ``True`` if the π-gate and the flow metrics disagreed in sign —
        the composer downgraded to NEUTRAL as a result.
    rationale
        Human-readable trace of which layer fired and why.
    refusal_reason
        Non-empty iff the decision was refused due to NaN/Inf inputs.
    """

    signal: CompositeSignal
    source_layer: str
    btc_result: BTCRuleResult
    phase_reading: GateReading
    flow_sign: int
    conflict_detected: bool
    rationale: tuple[str, ...]
    refusal_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal.value,
            "source_layer": self.source_layer,
            "btc_result": self.btc_result.to_dict(),
            "phase_reading": self.phase_reading.to_dict(),
            "flow_sign": self.flow_sign,
            "conflict_detected": self.conflict_detected,
            "rationale": list(self.rationale),
            "refusal_reason": self.refusal_reason,
        }


def _flow_sign(qilm: float, fmn: float, min_magnitude: float) -> int:
    """Return +1/−1/0 from the joint QILM+FMN sign agreement.

    Both must individually exceed ``min_magnitude`` in absolute value
    AND share the same sign. Anything else → 0.
    """
    if abs(qilm) < min_magnitude or abs(fmn) < min_magnitude:
        return 0
    if qilm > 0.0 and fmn > 0.0:
        return 1
    if qilm < 0.0 and fmn < 0.0:
        return -1
    return 0


def _phase_signal_sign(signal: Signal) -> int:
    if signal is Signal.LONG:
        return 1
    if signal is Signal.SHORT:
        return -1
    return 0


def _btc_to_composite(signal: BTCSignal) -> CompositeSignal:
    mapping: dict[BTCSignal, CompositeSignal] = {
        BTCSignal.LONG: CompositeSignal.LONG,
        BTCSignal.SHORT: CompositeSignal.SHORT,
        BTCSignal.NEUTRAL: CompositeSignal.NEUTRAL,
        BTCSignal.AVOID: CompositeSignal.AVOID,
    }
    return mapping[signal]


def compose_decision(
    snapshot: TradingSnapshot,
    config: TradingComposerConfig | None = None,
) -> CompositeDecision:
    """Fuse flow metrics + π-gate + BTC rules into one decision.

    Parameters
    ----------
    snapshot
        Full input bundle. NaN/Inf in any field → refusal.
    config
        Optional composer config; defaults to
        ``DEFAULT_TRADING_COMPOSER_CONFIG``.

    Returns
    -------
    CompositeDecision
        Signal + provenance + full sub-layer audit trail.
    """
    cfg = config or DEFAULT_TRADING_COMPOSER_CONFIG

    # ---- Fail-closed NaN guard at the boundary ---- #
    if snapshot.has_nan():
        empty_btc = BTCRuleResult(
            signal=BTCSignal.NEUTRAL,
            fired_rules=tuple(),
            rationale=tuple(),
            diagnostics={},
            refusal_reason="parent snapshot refused",
        )
        gate = PhaseEntryGate(cfg.phase_gate_config)
        # Evaluate on zeros so the gate can still report a consistent
        # NEUTRAL/NaN-aware reading for the audit trail.
        phase_reading = gate.evaluate(
            r_kuramoto=0.0,
            delta_h=0.0,
            kappa_mean=0.0,
            hurst=0.5,
        )
        return CompositeDecision(
            signal=CompositeSignal.NEUTRAL,
            source_layer="neutral",
            btc_result=empty_btc,
            phase_reading=phase_reading,
            flow_sign=0,
            conflict_detected=False,
            rationale=("snapshot contains NaN or Inf — refusing to decide",),
            refusal_reason="non-finite value in TradingSnapshot",
        )

    # ---- Layer 1: BTC rule engine ---- #
    btc_result = evaluate_btc_rules(snapshot.btc_snapshot, cfg.btc_rule_config)

    # Hard refusal: trap geometries always win.
    if btc_result.fired_rules and btc_result.fired_rules[0] is BTCRule.R02_OI_PRICE_DIVERGENCE_TRAP:
        gate = PhaseEntryGate(cfg.phase_gate_config)
        phase_reading = gate.evaluate(
            r_kuramoto=snapshot.r_kuramoto,
            delta_h=snapshot.delta_h,
            kappa_mean=snapshot.kappa_mean,
            hurst=snapshot.hurst,
        )
        return CompositeDecision(
            signal=CompositeSignal.AVOID,
            source_layer="btc_rules",
            btc_result=btc_result,
            phase_reading=phase_reading,
            flow_sign=_flow_sign(
                snapshot.qilm_latest,
                snapshot.fmn_latest,
                cfg.flow_min_magnitude,
            ),
            conflict_detected=False,
            rationale=btc_result.rationale,
        )

    # Any other BTC rule that fired directionally outranks the gate.
    if btc_result.signal in (BTCSignal.LONG, BTCSignal.SHORT):
        gate = PhaseEntryGate(cfg.phase_gate_config)
        phase_reading = gate.evaluate(
            r_kuramoto=snapshot.r_kuramoto,
            delta_h=snapshot.delta_h,
            kappa_mean=snapshot.kappa_mean,
            hurst=snapshot.hurst,
        )
        return CompositeDecision(
            signal=_btc_to_composite(btc_result.signal),
            source_layer="btc_rules",
            btc_result=btc_result,
            phase_reading=phase_reading,
            flow_sign=_flow_sign(
                snapshot.qilm_latest,
                snapshot.fmn_latest,
                cfg.flow_min_magnitude,
            ),
            conflict_detected=False,
            rationale=btc_result.rationale,
        )

    # ---- Layer 2: π-system phase gate ---- #
    gate = PhaseEntryGate(cfg.phase_gate_config)
    phase_reading = gate.evaluate(
        r_kuramoto=snapshot.r_kuramoto,
        delta_h=snapshot.delta_h,
        kappa_mean=snapshot.kappa_mean,
        hurst=snapshot.hurst,
    )
    phase_sign = _phase_signal_sign(phase_reading.signal)
    flow_sign = _flow_sign(
        snapshot.qilm_latest,
        snapshot.fmn_latest,
        cfg.flow_min_magnitude,
    )

    if phase_sign != 0:
        if phase_sign == flow_sign:
            # Confirmed by microstructure → commit.
            composite = CompositeSignal.LONG if phase_sign > 0 else CompositeSignal.SHORT
            return CompositeDecision(
                signal=composite,
                source_layer="phase_gate",
                btc_result=btc_result,
                phase_reading=phase_reading,
                flow_sign=flow_sign,
                conflict_detected=False,
                rationale=(
                    f"π-gate {phase_reading.signal.value.upper()} confirmed by "
                    f"QILM={snapshot.qilm_latest:+.3f} / "
                    f"FMN={snapshot.fmn_latest:+.3f}",
                ),
            )
        # π-gate fires but flow contradicts or is weak → downgrade.
        return CompositeDecision(
            signal=CompositeSignal.NEUTRAL,
            source_layer="phase_gate",
            btc_result=btc_result,
            phase_reading=phase_reading,
            flow_sign=flow_sign,
            conflict_detected=flow_sign != 0 and flow_sign != phase_sign,
            rationale=(
                f"π-gate {phase_reading.signal.value.upper()} not confirmed by "
                f"flow (QILM={snapshot.qilm_latest:+.3f}, "
                f"FMN={snapshot.fmn_latest:+.3f}) — downgrade to NEUTRAL",
            ),
        )

    # ---- Layer 3: flow metrics alone ---- #
    if flow_sign != 0:
        composite = CompositeSignal.LONG if flow_sign > 0 else CompositeSignal.SHORT
        return CompositeDecision(
            signal=composite,
            source_layer="flow_metrics",
            btc_result=btc_result,
            phase_reading=phase_reading,
            flow_sign=flow_sign,
            conflict_detected=False,
            rationale=(
                f"flow-only {composite.value.upper()}: "
                f"QILM={snapshot.qilm_latest:+.3f}, "
                f"FMN={snapshot.fmn_latest:+.3f}",
            ),
        )

    # ---- Nothing fires ---- #
    return CompositeDecision(
        signal=CompositeSignal.NEUTRAL,
        source_layer="neutral",
        btc_result=btc_result,
        phase_reading=phase_reading,
        flow_sign=0,
        conflict_detected=False,
        rationale=("no layer emitted a directional signal",),
    )


class TradingComposer:
    """Stateless OO facade around :func:`compose_decision`.

    Useful when callers want to hold onto a configured instance and
    feed it many snapshots — e.g. in a backtest loop.
    """

    def __init__(self, config: TradingComposerConfig | None = None) -> None:
        self._config = config or DEFAULT_TRADING_COMPOSER_CONFIG

    @property
    def config(self) -> TradingComposerConfig:
        return self._config

    def compose(self, snapshot: TradingSnapshot) -> CompositeDecision:
        return compose_decision(snapshot, self._config)
