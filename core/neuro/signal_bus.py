# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""NeuroSignalBus — Centralized neuromodulator coordination layer.

Implements a typed pub/sub signal bus that connects all neuroscience-inspired
subsystems into a unified, deterministic, configurable risk management
pipeline. Every controller publishes its state; every controller reads
the state of others.

Signal flow (biological analogy):
    Kuramoto R (market coherence) ─┐
    HPC PWPE (prediction error) ───┤
                                   ▼
    ┌─────────── NeuroSignalBus ───────────┐
    │  dopamine_rpe    : float  (reward)   │
    │  serotonin_level : float  (aversion) │
    │  gaba_inhibition : float  (braking)  │
    │  nak_energy      : float  (arousal)  │
    │  kuramoto_R      : float  (regime)   │
    │  hpc_pwpe        : float  (surprise) │
    │  ecs_free_energy : float  (homeost.) │
    │  stress_regime   : enum   (phase)    │
    └──────────────────────────────────────┘
                                   │
    ┌──────────────────────────────┘
    ▼
    Position sizing ← kelly * (0.5 + 0.5*R) * (1 - inhibition)
    Hold/Veto       ← serotonin > threshold
    Learning rate   ← base_lr * (1 + nak_energy/E_max)

Architecture:
    - Thread-safe: all reads/writes under RLock
    - Deterministic: signals are scalars with bounded ranges
    - Observable: full snapshot export for audit/telemetry
    - Configurable: all thresholds via YAML/dataclass

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class StressRegime(Enum):
    """Market stress regime derived from combined neuromodulator signals."""

    NORMAL = "normal"
    ELEVATED = "elevated"
    CRISIS = "crisis"
    RECOVERY = "recovery"


@dataclass
class NeuroSignals:
    """Immutable snapshot of all neuromodulator signals at a point in time.

    Each signal has a biological analogue and a bounded valid range:
        dopamine_rpe     ∈ [-1, 1]   — reward prediction error (TD error)
            INV-DA7 scope: ∂δ/∂r = 1 holds ONLY for the raw-TD path
            (DopamineController.compute_rpe). DopamineExecutionAdapter
            publishes tanh(scale * raw_rpe) into this same slot; for
            that path ∂δ/∂r = sech²(·) ≠ 1. Consumers that depend on
            the algebraic identity must read from the controller path,
            not from the adapter post-tanh value. See
            .claude/physics/INVARIANTS.yaml::INV-DA7 scope_note.
        serotonin_level  ∈ [0, 1]    — aversive state / risk aversion
        gaba_inhibition  ∈ [0, 1]    — action inhibition coefficient
        nak_energy       ∈ [0, 1]    — arousal / metabolic energy state
        kuramoto_R       ∈ [0, 1]    — market phase synchrony (order param)
        hpc_pwpe         ∈ [0, ∞)    — precision-weighted prediction error
        ecs_free_energy  ∈ [0, ∞)    — homeostatic free energy
        stress_regime    ∈ StressRegime — categorical regime label
    """

    dopamine_rpe: float = 0.0
    serotonin_level: float = 0.0
    gaba_inhibition: float = 0.0
    nak_energy: float = 0.5
    kuramoto_R: float = 0.5
    hpc_pwpe: float = 0.0
    ecs_free_energy: float = 0.0
    stress_regime: StressRegime = StressRegime.NORMAL
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["stress_regime"] = self.stress_regime.value
        return d


@dataclass
class BusConfig:
    """Configurable thresholds for cross-system signal integration.

    These govern how neuromodulator signals combine into trading decisions.
    All values have theoretical backing from computational neuroscience:

    - kelly_coherence_floor/ceil: Kuramoto R scaling for Kelly fraction
      Based on: synchronization → trend confidence (Breakspear 2010)
    - inhibition_position_scale: GABA gate on position size
      Based on: GABAergic inhibition of motor output (Mink 1996)
    - serotonin_hold_threshold: aversive veto threshold
      Based on: 5-HT patience hypothesis (Miyazaki et al. 2014)
    - dopamine_lr_modulation: RPE-based learning rate scaling
      Based on: DA modulates synaptic plasticity (Schultz 1997)
    - crisis_rpe_threshold: negative RPE triggering crisis regime
      Based on: phasic DA dips signal worse-than-expected (Schultz 2016)
    """

    kelly_coherence_floor: float = 0.3
    kelly_coherence_ceil: float = 0.8
    kelly_min_fraction: float = 0.1
    kelly_max_fraction: float = 1.0
    inhibition_position_scale: float = 1.0
    serotonin_hold_threshold: float = 0.7
    dopamine_lr_modulation: float = 0.5
    nak_lr_scale_max: float = 2.0
    crisis_rpe_threshold: float = -0.3
    crisis_serotonin_threshold: float = 0.8
    elevated_serotonin_threshold: float = 0.5
    pwpe_stress_scale: float = 0.1
    fe_recovery_threshold: float = 0.3


class NeuroSignalBus:
    """Thread-safe neuromodulator signal bus for cross-system coordination.

    Usage::

        bus = NeuroSignalBus()

        # Controllers publish their state
        bus.publish_dopamine(rpe=0.15)
        bus.publish_serotonin(level=0.42)
        bus.publish_gaba(inhibition=0.3)
        bus.publish_kuramoto(R=0.72)

        # Trading logic reads integrated signals
        signals = bus.snapshot()
        position_mult = bus.compute_position_multiplier()
        should_hold = bus.should_hold()
        lr = bus.compute_learning_rate(base_lr=1e-4)
    """

    def __init__(
        self,
        config: Optional[BusConfig] = None,
        logger: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self._config = config or BusConfig()
        self._lock = threading.RLock()
        self._signals = NeuroSignals(timestamp=time.time())
        self._logger = logger
        self._subscribers: Dict[str, List[Callable[[NeuroSignals], None]]] = {}
        self._history: List[NeuroSignals] = []
        self._max_history = 1000

    # ── Publishers ────────────────────────────────────────────────────

    def publish_dopamine(self, rpe: float) -> None:
        """Publish dopamine reward prediction error ∈ [-1, 1]."""
        with self._lock:
            self._signals.dopamine_rpe = max(-1.0, min(1.0, float(rpe)))
            self._update_regime()
            self._notify("dopamine")

    def publish_serotonin(self, level: float) -> None:
        """Publish serotonin level ∈ [0, 1]."""
        with self._lock:
            self._signals.serotonin_level = max(0.0, min(1.0, float(level)))
            self._update_regime()
            self._notify("serotonin")

    def publish_gaba(self, inhibition: float) -> None:
        """Publish GABA inhibition coefficient ∈ [0, 1]."""
        with self._lock:
            self._signals.gaba_inhibition = max(0.0, min(1.0, float(inhibition)))
            self._notify("gaba")

    def publish_nak(self, energy: float) -> None:
        """Publish NAk energy state ∈ [0, 1]."""
        with self._lock:
            self._signals.nak_energy = max(0.0, min(1.0, float(energy)))
            self._notify("nak")

    def publish_kuramoto(self, R: float) -> None:
        """Publish Kuramoto order parameter R ∈ [0, 1]."""
        with self._lock:
            self._signals.kuramoto_R = max(0.0, min(1.0, float(R)))
            self._notify("kuramoto")

    def publish_hpc(self, pwpe: float) -> None:
        """Publish HPC precision-weighted prediction error ∈ [0, ∞)."""
        with self._lock:
            self._signals.hpc_pwpe = max(0.0, float(pwpe))
            self._update_regime()
            self._notify("hpc")

    def publish_ecs(self, free_energy: float) -> None:
        """Publish ECS free energy ∈ [0, ∞)."""
        with self._lock:
            self._signals.ecs_free_energy = max(0.0, float(free_energy))
            self._notify("ecs")

    # ── Readers / Integrated Decision Functions ───────────────────────

    def snapshot(self) -> NeuroSignals:
        """Return immutable snapshot of current signal state."""
        with self._lock:
            s = self._signals
            return NeuroSignals(
                dopamine_rpe=s.dopamine_rpe,
                serotonin_level=s.serotonin_level,
                gaba_inhibition=s.gaba_inhibition,
                nak_energy=s.nak_energy,
                kuramoto_R=s.kuramoto_R,
                hpc_pwpe=s.hpc_pwpe,
                ecs_free_energy=s.ecs_free_energy,
                stress_regime=s.stress_regime,
                timestamp=time.time(),
            )

    def should_hold(self) -> bool:
        """Determine if trading should be halted (serotonin veto).

        Implements the 5-HT patience hypothesis: high serotonin signals
        that waiting (not trading) is the optimal strategy.
        """
        with self._lock:
            cfg = self._config
            s = self._signals
            # Primary: serotonin aversive veto
            serotonin_veto = s.serotonin_level > cfg.serotonin_hold_threshold
            # Secondary: crisis regime always holds
            crisis_veto = s.stress_regime == StressRegime.CRISIS
            return serotonin_veto or crisis_veto

    def compute_position_multiplier(self, kelly_base: float = 1.0) -> float:
        """Compute position size multiplier from integrated neuro signals.

        Formula:
            if should_hold():  return 0.0     # Protector veto (INV-YV1 L2)
            mult = kelly_base
                   * coherence_scale(R)      # Kuramoto regime confidence
                   * (1 - gaba_inhibition)    # GABA braking
                   * regime_scale             # stress regime dampening

        The Protector veto (serotonin aversion / crisis regime) has
        UNCONDITIONAL priority over the Generator (Kelly sizing) per the
        maintenance hierarchy (CLAUDE.md §0, INV-YV1 Layer 2): a firing
        Protector zeroes the position, it does not merely dampen it.

        Returns:
            float ∈ [0, kelly_base]
        """
        with self._lock:
            cfg = self._config
            s = self._signals

            # 0. Protector veto — INV-YV1 maintenance hierarchy (CLAUDE.md §0):
            #    Protectors have UNCONDITIONAL priority over Generators. The
            #    serotonin aversive veto and the crisis regime must be able to
            #    HALT sizing, not merely dampen it. Before this, should_hold()
            #    was computed but never reached the multiplier the production
            #    oracle multiplies (geosync_oracle.py), so the veto was advisory
            #    only — a Generator could keep a full position while a Protector
            #    was firing. RLock is reentrant, so should_hold() is safe here.
            if self.should_hold():
                if self._logger:
                    self._logger("neuro.protector_veto", 0.0)
                return 0.0

            # 1. Kuramoto coherence → Kelly fraction scaling
            #    R < floor → minimum fraction; R > ceil → full fraction
            #    Linear interpolation between floor and ceil
            if s.kuramoto_R <= cfg.kelly_coherence_floor:
                coherence_scale = cfg.kelly_min_fraction
            elif s.kuramoto_R >= cfg.kelly_coherence_ceil:
                coherence_scale = cfg.kelly_max_fraction
            else:
                t = (s.kuramoto_R - cfg.kelly_coherence_floor) / (
                    cfg.kelly_coherence_ceil - cfg.kelly_coherence_floor
                )
                coherence_scale = cfg.kelly_min_fraction + t * (
                    cfg.kelly_max_fraction - cfg.kelly_min_fraction
                )

            # 2. GABA inhibition gate
            gaba_gate = 1.0 - s.gaba_inhibition * cfg.inhibition_position_scale

            # 3. Stress regime dampening
            regime_scale = {
                StressRegime.NORMAL: 1.0,
                StressRegime.ELEVATED: 0.6,
                StressRegime.CRISIS: 0.1,
                StressRegime.RECOVERY: 0.4,
            }.get(s.stress_regime, 0.5)

            result = kelly_base * coherence_scale * max(0.0, gaba_gate) * regime_scale
            if self._logger:
                self._logger("neuro.position_multiplier", result)
            return max(0.0, result)

    def compute_learning_rate(self, base_lr: float) -> float:
        """Compute adaptive learning rate from neuromodulator state.

        Formula:
            lr = base_lr
                 * (1 + dopamine_modulation * |RPE|)  # surprise → faster learning
                 * min(nak_lr_scale_max, 1 + energy)   # arousal → exploration
                 * pwpe_scale                           # uncertainty → careful

        Based on: dopamine modulates synaptic plasticity magnitude
        (Schultz 1997; Friston 2009 precision-weighting)
        """
        with self._lock:
            cfg = self._config
            s = self._signals

            # Dopamine RPE magnitude scales learning (Schultz 1997)
            da_scale = 1.0 + cfg.dopamine_lr_modulation * abs(s.dopamine_rpe)

            # NAk energy/arousal scales exploration (Aston-Jones & Cohen 2005)
            nak_scale = min(cfg.nak_lr_scale_max, 1.0 + s.nak_energy)

            # High PWPE → reduce lr (uncertain → conservative updates)
            pwpe_scale = 1.0 / (1.0 + cfg.pwpe_stress_scale * s.hpc_pwpe)

            return base_lr * da_scale * nak_scale * pwpe_scale

    # ── Regime Detection ──────────────────────────────────────────────

    def _update_regime(self) -> None:
        """Derive stress regime from combined signals (no lock — called under lock)."""
        cfg = self._config
        s = self._signals

        # Crisis: large negative RPE + high serotonin + high PWPE
        if (
            s.dopamine_rpe < cfg.crisis_rpe_threshold
            and s.serotonin_level > cfg.crisis_serotonin_threshold
        ):
            new_regime = StressRegime.CRISIS
        # Recovery: was in crisis, free energy decreasing
        elif (
            s.stress_regime == StressRegime.CRISIS and s.ecs_free_energy < cfg.fe_recovery_threshold
        ):
            new_regime = StressRegime.RECOVERY
        # Elevated: moderate serotonin or negative RPE
        elif s.serotonin_level > cfg.elevated_serotonin_threshold or s.dopamine_rpe < 0:
            new_regime = StressRegime.ELEVATED
        else:
            new_regime = StressRegime.NORMAL

        if new_regime != s.stress_regime:
            old = s.stress_regime
            s.stress_regime = new_regime
            if self._logger:
                self._logger(f"neuro.regime_transition.{old.value}_to_{new_regime.value}", 1.0)

        s.timestamp = time.time()

        # Archive to history
        self._history.append(
            NeuroSignals(
                dopamine_rpe=s.dopamine_rpe,
                serotonin_level=s.serotonin_level,
                gaba_inhibition=s.gaba_inhibition,
                nak_energy=s.nak_energy,
                kuramoto_R=s.kuramoto_R,
                hpc_pwpe=s.hpc_pwpe,
                ecs_free_energy=s.ecs_free_energy,
                stress_regime=s.stress_regime,
                timestamp=s.timestamp,
            )
        )
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    # ── Subscription / Observability ──────────────────────────────────

    def subscribe(self, channel: str, callback: Callable[[NeuroSignals], None]) -> None:
        """Subscribe to signal updates on a channel (dopamine, serotonin, etc.)."""
        with self._lock:
            self._subscribers.setdefault(channel, []).append(callback)

    def _notify(self, channel: str) -> None:
        """Notify subscribers (called under lock)."""
        for cb in self._subscribers.get(channel, []):
            try:
                cb(self._signals)
            except Exception:
                pass

    def get_history(self, n: int = 100) -> List[Dict[str, Any]]:
        """Return last n signal snapshots as dicts for audit/telemetry."""
        with self._lock:
            return [s.to_dict() for s in self._history[-n:]]

    def reset(self) -> None:
        """Reset all signals to defaults."""
        with self._lock:
            self._signals = NeuroSignals(timestamp=time.time())
            self._history.clear()
