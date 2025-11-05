"""Main WML controller with risk-freeze and adaptive optimization."""

from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
import time

from .config import WMLConfig
from .regime import RegimeDetector, Regime
from .metrics import Telemetry
from .mfe import free_energy
from .actions import Action, ActionPlan, NoOpActions, guarded_apply
from .audit import AuditLogger
from .eventbus import EventBus


# Type alias for risk freeze function
RiskFreezeFn = Callable[[], bool]


@dataclass(slots=True)
class PathState:
    """State for a single hot path."""

    myelin: float = 0.0
    recent_usefulness: float = 0.0
    inactive_for: float = 0.0
    last_regime: Optional[Regime] = None
    last_plan: Optional[ActionPlan] = None
    last_apply_ts: float = 0.0
    control_failures: int = 0  # NEW: Track consecutive control failures


class TelemetryProbe:
    """Interface for probing tentative system states."""

    def measure_after(
        self, path: str, tentative_myelin: float, plan: ActionPlan
    ) -> Telemetry:
        """Measure telemetry after hypothetically applying the plan.

        Args:
            path: Hot path identifier
            tentative_myelin: Proposed myelin value
            plan: Proposed action plan

        Returns:
            Predicted telemetry after applying the plan
        """
        raise NotImplementedError


@dataclass
class WML:
    """Weighted Myelin Layer - adaptive optimization controller.

    This implements neurobiologically-inspired adaptive optimization:
    - Plasticity (Hebbian learning + synaptic decay)
    - Threat response (regime-based modulation)
    - Free energy minimization (multi-objective optimization)
    - Risk freeze (amygdala-like threat override)
    """

    config: WMLConfig
    detector: RegimeDetector
    actions: Action = field(default_factory=NoOpActions)
    audit: Optional[AuditLogger] = None
    bus: Optional[EventBus] = None
    risk_freeze_fn: Optional[RiskFreezeFn] = None  # NEW: Risk freeze callback
    state: Dict[str, PathState] = field(default_factory=dict)

    def get_state(self, path: str) -> PathState:
        """Get or create state for a path."""
        if path not in self.state:
            self.state[path] = PathState()
        return self.state[path]

    def schedule_params(self, regime: Regime) -> Dict[str, float]:
        """Get plasticity parameters for the current regime."""
        return self.config.plasticity_schedule.get(
            regime.name, self.config.plasticity_schedule["TREND"]
        )

    def plan_for(self, regime: Regime, new_m: float) -> ActionPlan:
        """Generate action plan based on regime and myelin level.

        Args:
            regime: Current system regime
            new_m: Proposed myelin value (0.0 to 1.0)

        Returns:
            ActionPlan with timing, conduct, and metabolic adjustments
        """
        # Base plan scales with myelin
        timing = {
            "batch_flush_ms": max(1, int(10 - 8 * new_m)),
            "ack_rate": 1 + int(5 * new_m),
        }
        conduct = {
            "fusion_depth": 1 + int(3 * new_m),
            "pinning": new_m > 0.5,
            "zero_copy": new_m > 0.7,
        }
        metabolic = {
            "prefetch_lead_ms": int(2 + 10 * new_m),
            "warm_pool": new_m > 0.6,
        }

        # Regime-specific constraints
        if regime == Regime.VOLATILE:
            timing["batch_flush_ms"] = max(timing["batch_flush_ms"], 5)
            conduct["fusion_depth"] = min(conduct["fusion_depth"], 2)
        elif regime == Regime.SHOCK:
            timing["batch_flush_ms"] = max(timing["batch_flush_ms"], 8)
            conduct["fusion_depth"] = 1
            conduct["zero_copy"] = False
            metabolic["warm_pool"] = False

        return ActionPlan(timing=timing, conduct=conduct, metabolic=metabolic)

    def step(self, path: str, current: Telemetry, probe: TelemetryProbe) -> bool:
        """Execute one WML optimization step.

        This implements the core adaptive optimization loop:
        1. Detect regime
        2. Check risk freeze
        3. Update myelin (plasticity + decay)
        4. Generate action plan
        5. Probe expected outcome
        6. Apply if free energy improves

        Args:
            path: Hot path identifier
            current: Current telemetry
            probe: Probe for testing tentative states

        Returns:
            True if optimization was applied, False otherwise
        """
        s = self.get_state(path)
        regime = self.detector.detect(current, s.last_regime)
        s.last_regime = regime

        # RISK-FREEZE: Override all learning if risk conditions are met
        if (
            self.config.risk_freeze_enabled
            and self.risk_freeze_fn
            and self.risk_freeze_fn()
        ):
            if self.audit:
                self.audit.log("WML_FROZEN", {"path": path, "regime": regime.name})
            if self.bus:
                self.bus.emit("WML_FROZEN", {"path": path, "regime": regime.name})
            return False

        # Get plasticity parameters for current regime
        sched = self.schedule_params(regime)
        eta = sched.get("eta", 0.02)
        lam = sched.get("lambda_decay", 0.005)
        m_min = self.config.bounds.get("m_min", 0.0)
        m_max = self.config.bounds.get("m_max", 1.0)

        # Update myelin: LTP (Hebbian) + LTD (decay)
        u = max(0.0, s.recent_usefulness)
        delta = current.pnl_delta
        tentative = s.myelin + eta * delta * u - lam * s.inactive_for
        tentative = min(m_max, max(m_min, tentative))

        # Generate action plan
        plan = self.plan_for(regime, tentative)

        # Skip if plan hasn't changed and we're within min apply interval
        now = time.time()
        if (
            s.last_plan == plan
            and abs(tentative - s.myelin) < 1e-6
            and (now - s.last_apply_ts) < self.config.min_apply_interval_s
        ):
            return False

        # Calculate current and predicted free energy
        F_now = free_energy(
            current, self.config.mfe_alpha, self.config.mfe_beta, self.config.gamma_is
        )
        after = probe.measure_after(path, tentative, plan)
        F_try = free_energy(
            after, self.config.mfe_alpha, self.config.mfe_beta, self.config.gamma_is
        )

        # Accept if free energy improves (relative OR absolute threshold)
        rel_ok = F_try < F_now * (1.0 - self.config.eps_rel)
        abs_ok = F_try < (F_now - self.config.mfe_margin)
        accept = rel_ok or abs_ok

        applied = False
        if accept:
            try:
                with guarded_apply(self.actions, path, plan):
                    s.myelin = tentative
                    # Update usefulness and activity tracking
                    s.recent_usefulness = max(
                        0.0, u * 0.8 + (1.0 if delta > 0 else 0.0)
                    )
                    s.inactive_for = (
                        0.0 if delta > 0 else min(60.0, s.inactive_for + 1.0)
                    )
                    s.last_plan = plan
                    s.last_apply_ts = now
                    s.control_failures = 0
                applied = True
            except Exception as e:
                s.control_failures += 1
                # Log the specific error for debugging
                if self.audit:
                    self.audit.log(
                        "WML_APPLY_ERROR",
                        {
                            "path": path,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "failures": s.control_failures,
                        },
                    )

                # AUTO-FREEZE: After repeated control failures, stop trying
                if s.control_failures >= self.config.auto_freeze_fails:
                    if self.audit:
                        self.audit.log(
                            "WML_AUTO_FREEZE",
                            {"path": path, "fails": s.control_failures},
                        )
                    if self.bus:
                        self.bus.emit("WML_AUTO_FREEZE", {"path": path})
                applied = False

            # Audit the decision
            if self.audit:
                self.audit.log(
                    "WML_APPLY",
                    {
                        "path": path,
                        "regime": regime.name,
                        "F_now": F_now,
                        "F_try": F_try,
                        "dF": F_try - F_now,
                        "dp99": after.p99 - current.p99,
                        "djitter": after.jitter - current.jitter,
                        "dIS_bp": after.is_bp - current.is_bp,
                        "myelin_new": s.myelin,
                    },
                )
            if self.bus:
                self.bus.emit("WML_APPLY", {"path": path, "regime": regime.name})
        else:
            # Decay usefulness when we don't apply
            s.recent_usefulness = max(0.0, u * 0.9)
            s.inactive_for = min(60.0, s.inactive_for + 1.0)

            if self.audit:
                self.audit.log(
                    "WML_REJECTED",
                    {
                        "path": path,
                        "regime": regime.name,
                        "F_now": F_now,
                        "F_try": F_try,
                        "dF": F_try - F_now,
                        "dp99": after.p99 - current.p99,
                        "djitter": after.jitter - current.jitter,
                        "dIS_bp": after.is_bp - current.is_bp,
                    },
                )
            if self.bus:
                self.bus.emit("WML_REJECTED", {"path": path, "regime": regime.name})

        return applied
