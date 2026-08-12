"""Risk gate middleware for OTP order router integration.

Sits between strategy signal and order submission. Applies GeoSync
regime classification as a position-sizing gate.

Logic:
  METASTABLE + risk_scalar > 0.7  → pass, full size
  COHERENT   + risk_scalar > 0.5  → pass, reduced size (×0.6)
  DECOHERENT                      → block, log reason
  CRITICAL                        → block, alert
  signal_unavailable              → block (fail-closed)

Invariants (enforced, never relaxed):
  - fail_closed=True: no signal = no trade
  - adjusted_size <= intended_size ALWAYS (risk gate never amplifies)
  - risk_scalar from gamma distance (derived, never assigned)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coherence_bridge.physics_contract import BridgeDecision, validate_physics_contract

if TYPE_CHECKING:
    from coherence_bridge.engine_interface import SignalEngine

logger = logging.getLogger("coherence_bridge.risk_gate")


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Result of risk gate evaluation."""

    allowed: bool
    adjusted_size: float
    reason: str
    regime: str
    risk_scalar: float


class CoherenceRiskGate:
    """Middleware between OTP strategy and order submission.

    Parameters
    ----------
    engine
        SignalEngine providing regime signals.
    fail_closed
        If True (default), missing signal → block order.
    metastable_threshold
        Minimum risk_scalar to pass in METASTABLE regime.
    coherent_threshold
        Minimum risk_scalar to pass in COHERENT regime.
    coherent_size_factor
        Size multiplier applied in COHERENT regime (reduced vs full).
    """

    #: Env flag that opts INTO the test-only fail-open harness. Production code
    #: must never set it; without it, fail_closed=False raises at construction.
    FAIL_OPEN_TEST_ENV = "GEOSYNC_ALLOW_FAIL_OPEN_TEST_ONLY"

    def __init__(
        self,
        engine: SignalEngine,
        *,
        fail_closed: bool = True,
        metastable_threshold: float = 0.7,
        coherent_threshold: float = 0.5,
        coherent_size_factor: float = 0.6,
    ) -> None:
        # Fail-open is forbidden by construction in production: a missing signal
        # must always block the order. fail_closed=False is a TEST-ONLY harness
        # mode and is rejected unless the explicit test env flag is set (see
        # UnsafeCoherenceRiskGateHarness). This makes the safety property a
        # constructor invariant, not a matter of caller discipline.
        if not fail_closed and os.environ.get(self.FAIL_OPEN_TEST_ENV) != "1":
            raise RuntimeError(
                "CoherenceRiskGate fail-open mode (fail_closed=False) is forbidden "
                "in production — a missing signal must block the order. It is a "
                f"test-only harness: set {self.FAIL_OPEN_TEST_ENV}=1 (or use "
                "UnsafeCoherenceRiskGateHarness) to use it deliberately in a test."
            )
        self.engine = engine
        self.fail_closed = fail_closed
        self.metastable_threshold = metastable_threshold
        self.coherent_threshold = coherent_threshold
        self.coherent_size_factor = coherent_size_factor

    def apply(self, instrument: str, intended_size: float) -> GateDecision:
        """Evaluate whether an order should proceed and at what size.

        Returns GateDecision with:
          allowed: bool — True if order can proceed
          adjusted_size: float — always <= intended_size
          reason: str — human-readable explanation
          regime: str — current regime
          risk_scalar: float — current risk_scalar
        """
        sig = self.engine.get_signal(instrument)

        # Fail-closed: no signal = no trade
        if sig is None:
            if self.fail_closed:
                return GateDecision(
                    allowed=False,
                    adjusted_size=0.0,
                    reason=f"No signal available for {instrument} (fail-closed)",
                    regime="UNAVAILABLE",
                    risk_scalar=0.0,
                )
            return GateDecision(
                allowed=True,
                adjusted_size=intended_size,
                reason="No signal, fail-open mode",
                regime="UNAVAILABLE",
                risk_scalar=1.0,
            )

        regime = str(sig.get("regime", "UNKNOWN"))

        # ── INV-CBR1 enforced FIRST (runtime, not just unit-tested source) ──
        # The physics-contract gate is the authoritative fail-closed boundary:
        # an out-of-band signal (R∉[0,1], negative/non-finite gamma, Ollivier
        # κ>1) is HARD-BLOCKED here, at the real order-sizing consumer, before
        # any regime logic. Sizing then uses the verdict's safe_risk_scalar —
        # never the relayed raw risk-scalar field (which is advisory telemetry).
        verdict = validate_physics_contract(sig)
        if verdict.decision is BridgeDecision.NO_GO:
            logger.warning(
                "RISK GATE BLOCK: %s INVALID_PHYSICS_CONTRACT %s",
                instrument,
                verdict.reasons,
            )
            return GateDecision(
                allowed=False,
                adjusted_size=0.0,
                reason="INVALID_PHYSICS_CONTRACT: " + "; ".join(verdict.reasons),
                regime=regime,
                risk_scalar=0.0,
            )
        risk_scalar = verdict.safe_risk_scalar

        # CRITICAL → block, alert
        if regime == "CRITICAL":
            logger.warning(
                "RISK GATE BLOCK: %s regime=CRITICAL risk=%.3f",
                instrument,
                risk_scalar,
            )
            return GateDecision(
                allowed=False,
                adjusted_size=0.0,
                reason=(
                    f"CRITICAL regime: herding detected (R={sig.get('order_parameter_R', 0):.3f})"
                ),
                regime=regime,
                risk_scalar=risk_scalar,
            )

        # DECOHERENT → block
        if regime == "DECOHERENT":
            return GateDecision(
                allowed=False,
                adjusted_size=0.0,
                reason="DECOHERENT regime: no signal edge (low R, high entropy)",
                regime=regime,
                risk_scalar=risk_scalar,
            )

        # UNKNOWN → block
        if regime == "UNKNOWN":
            return GateDecision(
                allowed=False,
                adjusted_size=0.0,
                reason="UNKNOWN regime: gamma non-finite or classification failed",
                regime=regime,
                risk_scalar=risk_scalar,
            )

        # METASTABLE → pass if risk_scalar above threshold
        if regime == "METASTABLE":
            if risk_scalar >= self.metastable_threshold:
                size = min(intended_size, intended_size * risk_scalar)
                return GateDecision(
                    allowed=True,
                    adjusted_size=size,
                    reason=f"METASTABLE: gamma near 1.0, risk={risk_scalar:.3f}",
                    regime=regime,
                    risk_scalar=risk_scalar,
                )
            return GateDecision(
                allowed=False,
                adjusted_size=0.0,
                reason=(
                    f"METASTABLE but risk_scalar={risk_scalar:.3f} < {self.metastable_threshold}"
                ),
                regime=regime,
                risk_scalar=risk_scalar,
            )

        # COHERENT → pass with reduced size if above threshold
        if regime == "COHERENT":
            if risk_scalar >= self.coherent_threshold:
                size = min(
                    intended_size,
                    intended_size * risk_scalar * self.coherent_size_factor,
                )
                return GateDecision(
                    allowed=True,
                    adjusted_size=size,
                    reason=f"COHERENT: high sync, reduced size ×{self.coherent_size_factor}",
                    regime=regime,
                    risk_scalar=risk_scalar,
                )
            return GateDecision(
                allowed=False,
                adjusted_size=0.0,
                reason=f"COHERENT but risk_scalar={risk_scalar:.3f} < {self.coherent_threshold}",
                regime=regime,
                risk_scalar=risk_scalar,
            )

        # Fallback: unknown regime → block (defensive)
        return GateDecision(
            allowed=False,
            adjusted_size=0.0,
            reason=f"Unrecognized regime: {regime}",
            regime=regime,
            risk_scalar=risk_scalar,
        )


class UnsafeCoherenceRiskGateHarness:
    """TEST-ONLY context manager that constructs a fail-OPEN risk gate.

    Fail-open is forbidden in production (a missing signal must block the order),
    so :class:`CoherenceRiskGate` raises on ``fail_closed=False`` unless the
    ``GEOSYNC_ALLOW_FAIL_OPEN_TEST_ONLY`` env flag is set. This harness sets that
    flag for the duration of a ``with`` block and restores it afterwards, so the
    only way to obtain a fail-open gate is through this loudly-named, scoped
    helper — never silently in a production code path.

    Usage (tests only)::

        with UnsafeCoherenceRiskGateHarness(engine) as gate:
            decision = gate.apply("EURUSD", 1.0)
    """

    def __init__(self, engine: SignalEngine, **kwargs: float) -> None:
        self._engine = engine
        self._kwargs = kwargs
        self._prev: str | None = None

    def __enter__(self) -> CoherenceRiskGate:
        self._prev = os.environ.get(CoherenceRiskGate.FAIL_OPEN_TEST_ENV)
        os.environ[CoherenceRiskGate.FAIL_OPEN_TEST_ENV] = "1"
        return CoherenceRiskGate(self._engine, fail_closed=False, **self._kwargs)

    def __exit__(self, *exc: object) -> None:
        if self._prev is None:
            os.environ.pop(CoherenceRiskGate.FAIL_OPEN_TEST_ENV, None)
        else:
            os.environ[CoherenceRiskGate.FAIL_OPEN_TEST_ENV] = self._prev
