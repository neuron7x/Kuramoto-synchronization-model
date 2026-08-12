"""Neuro-Homeostatic Stabilizer (NHS) — E/I balance controller for trading.

Maintains dynamic equilibrium between excitatory drive (take risk, trade)
and inhibitory drive (protect capital, observe) using the same
neurotransmitter proxy signals that GeoSync's NeuroSignalBus provides.

Biological analogy:
  Excitatory (glutamate) = dopamine RPE + signal_strength + risk_scalar
  Inhibitory (GABA)      = serotonin veto + uncertainty + regime surprise

  E/I ratio > 1.0 → system is excited → reduce kelly, tighten stops
  E/I ratio < 1.0 → system is inhibited → appropriate, proceed normally
  E/I ratio ≈ 1.0 → homeostatic balance → optimal trading zone

  When E/I diverges beyond threshold → dissociative shield activates:
  all positions zeroed, system enters protective dormancy.

Integration:
  NHS sits between UncertaintyEstimator and CoherenceRiskGate.
  It modulates kelly_fraction and can force full shutdown.

  Pipeline: signal → uncertainty → NHS.update() → kelly_mult → risk_gate

Physics connection:
  E/I balance maps to edge of criticality in Kuramoto model:
  R ≈ R_c (critical coupling) = system near phase transition.
  Too excitatory → supercritical → herding → crash.
  Too inhibitory → subcritical → no signal → paralysis.
  NHS keeps the system at R ≈ R_c where information processing is maximal.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


def _shortest_signed_arc(a: float, b: float) -> float:
    """Signed shortest arc from `a` to `b` on the unit circle, in (-π, π].

    Defined locally so NHS does not depend on the reset-wave engine module.
    Used by `re_adaptation_to_baseline` to compare phases on the manifold
    rather than as raw real-line numbers; this guards the safety-lock gate
    against false triggers on equivalent phases that differ by 2π·k.
    """
    return ((b - a + math.pi) % (2.0 * math.pi)) - math.pi


@dataclass(frozen=True, slots=True)
class HomeostaticState:
    """Snapshot of E/I balance at one time step."""

    excitatory: float  # aggregate drive to trade [0, ∞)
    inhibitory: float  # aggregate drive to protect [0, ∞)
    ei_ratio: float  # E/I balance (1.0 = homeostasis)
    kelly_multiplier: float  # position size adjustment [0, 1]
    regime: str  # "HOMEOSTATIC" | "EXCITATORY" | "INHIBITORY" | "DISSOCIATED"
    entropy: float  # signal entropy (information content)


@dataclass(frozen=True, slots=True)
class ResetWaveReport:
    """Result of decentralized reset wave synchronization."""

    activation_trigger: str
    write_ops_inhibited: bool
    average_phase_error: float
    reset_energy: float
    pre_reset_energy: float
    post_reset_energy: float
    energy_delta: float
    converged: bool
    node_count: int
    safety_lock: bool


class NeuroHomeostaticStabilizer:
    """E/I balance controller that modulates position sizing.

    Parameters
    ----------
    ei_target
        Target E/I ratio (1.0 = perfect balance).
    dissociation_threshold
        E/I ratio above which system enters protective shutdown.
    recovery_threshold
        E/I ratio below which system can exit dissociation.
    entropy_cutoff
        Signal entropy above which dissociative shield activates.
    window_size
        Rolling window for entropy estimation.
    """

    def __init__(
        self,
        *,
        ei_target: float = 1.0,
        dissociation_threshold: float = 3.0,
        recovery_threshold: float = 1.5,
        entropy_cutoff: float = 2.5,
        window_size: int = 50,
    ) -> None:
        self.ei_target = ei_target
        self.dissociation_threshold = dissociation_threshold
        self.recovery_threshold = recovery_threshold
        self.entropy_cutoff = entropy_cutoff

        self._dissociated = False
        self._signal_history: deque[float] = deque(maxlen=window_size)
        self._ei_history: deque[float] = deque(maxlen=window_size)

    def update(self, signal: dict[str, object]) -> HomeostaticState:
        """Compute E/I balance from signal and return homeostatic state.

        Excitatory drive (reasons to trade):
          - risk_scalar: how close gamma is to metastable (edge quality)
          - |signal_strength|: directional conviction
          - regime_confidence: model certainty

        Inhibitory drive (reasons to protect):
          - 1 - regime_confidence: model uncertainty
          - ambiguity from gamma velocity (if available)
          - inverse of risk_scalar: distance from metastable

        The balance determines kelly_multiplier:
          E/I ≈ 1.0 → kelly_mult = 1.0 (full position)
          E/I > threshold → kelly_mult → 0 (protective shutdown)
          E/I < 0.5 → kelly_mult = 0.8 (slightly cautious, system too quiet)
        """
        risk = _to_float(signal.get("risk_scalar"))
        confidence = _to_float(signal.get("regime_confidence"))
        strength = abs(_to_float(signal.get("signal_strength")))
        gamma = _to_float(signal.get("gamma"))

        # Excitatory: reasons to act
        excitatory = risk * 0.4 + strength * 0.3 + confidence * 0.3

        # Inhibitory: reasons to hold
        # Baseline floor 0.3 — even perfect conditions deserve caution
        inhibitory = (
            0.3  # baseline prudence (always-on GABA tone)
            + (1.0 - confidence) * 0.25
            + (1.0 - risk) * 0.25
            + _gamma_instability(gamma) * 0.2
        )

        # E/I ratio: balanced ≈ 1.0
        ei_ratio = excitatory / max(inhibitory, 1e-9)

        # Track history
        self._ei_history.append(ei_ratio)
        self._signal_history.append(risk)

        # Entropy of recent risk_scalar values
        entropy = self._compute_entropy()

        # Dissociative shield check
        if self._dissociated:
            if ei_ratio < self.recovery_threshold and entropy < self.entropy_cutoff:
                self._dissociated = False
            else:
                return HomeostaticState(
                    excitatory=0.0,
                    inhibitory=1.0,
                    ei_ratio=0.0,
                    kelly_multiplier=0.0,
                    regime="DISSOCIATED",
                    entropy=round(entropy, 4),
                )

        if ei_ratio > self.dissociation_threshold or entropy > self.entropy_cutoff:
            self._dissociated = True
            return HomeostaticState(
                excitatory=round(excitatory, 4),
                inhibitory=round(inhibitory, 4),
                ei_ratio=round(ei_ratio, 4),
                kelly_multiplier=0.0,
                regime="DISSOCIATED",
                entropy=round(entropy, 4),
            )

        # Kelly multiplier from E/I balance
        # Optimal at ei_ratio ≈ 1.0 (homeostasis)
        # Decays as ratio deviates from target
        distance = abs(ei_ratio - self.ei_target)
        kelly_mult = max(0.1, 1.0 - distance * 0.5)
        kelly_mult = min(1.0, kelly_mult)

        # Classify regime
        if 0.7 <= ei_ratio <= 1.3:
            regime = "HOMEOSTATIC"
        elif ei_ratio > 1.3:
            regime = "EXCITATORY"
        else:
            regime = "INHIBITORY"

        return HomeostaticState(
            excitatory=round(excitatory, 4),
            inhibitory=round(inhibitory, 4),
            ei_ratio=round(ei_ratio, 4),
            kelly_multiplier=round(kelly_mult, 4),
            regime=regime,
            entropy=round(entropy, 4),
        )

    def _compute_entropy(self) -> float:
        """Shannon entropy of discretized risk_scalar history.

        High entropy = signal is noisy/unpredictable → protective mode.
        Low entropy = signal is stable/predictable → trading mode.
        """
        if len(self._signal_history) < 10:
            return 2.0  # assume high entropy when cold

        # Discretize into 10 bins
        values = list(self._signal_history)
        bins = [0] * 10
        for v in values:
            idx = min(9, max(0, int(v * 10)))
            bins[idx] += 1

        total = len(values)
        entropy = 0.0
        for count in bins:
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        return entropy

    @property
    def is_dissociated(self) -> bool:
        """True if system is in protective shutdown."""
        return self._dissociated

    def re_adaptation_to_baseline(
        self,
        node_phases: list[float],
        baseline_phases: list[float],
        *,
        serotonin_gain: float = 1.0,
        convergence_tol: float = 0.05,
        max_phase_error: float = math.pi,
    ) -> ResetWaveReport:
        """Run decentralized reset wave to pull nodes back to baseline phase.

        Implements a Kuramoto-style phase correction:
            S_reset = mean(sin(theta_base - theta_i)) * gamma_serotonin

        Thermodynamic invariant (closed digital system analogue):
            pre_reset_energy >= post_reset_energy
        where energy is a phase potential based on (1 - cos(delta_phase)).
        """
        if len(node_phases) != len(baseline_phases):
            raise ValueError("node_phases and baseline_phases must have equal length")
        if not node_phases:
            raise ValueError("at least one node phase is required")
        if serotonin_gain <= 0:
            raise ValueError("serotonin_gain must be > 0")
        if max_phase_error <= 0:
            raise ValueError("max_phase_error must be > 0")

        # 2026-05-05 cycle #6: phase_diffs use the shortest signed arc on
        # the circle, not naive subtraction. The energy fields (1 - cos,
        # sin) are 2π-periodic and were already manifold-invariant, but
        # the SAFETY-LOCK gate compared `abs(naive_diff)` against
        # max_phase_error and so could trigger on phases that are close
        # on the manifold but linearly far in R. That made re_adaptation
        # falsely safety-lock when a caller normalised phases to a
        # different 2π window, with downstream impact on trade gating.
        phase_diffs = [
            _shortest_signed_arc(node, base) for node, base in zip(node_phases, baseline_phases)
        ]
        phase_errors = [abs(diff) for diff in phase_diffs]
        if any(err > max_phase_error for err in phase_errors):
            pre_reset_energy = serotonin_gain * (
                sum(1.0 - math.cos(diff) for diff in phase_diffs) / len(phase_diffs)
            )
            return ResetWaveReport(
                activation_trigger="NeuroHomeostaticStabilizer",
                write_ops_inhibited=True,
                average_phase_error=round(sum(phase_errors) / len(phase_errors), 6),
                reset_energy=0.0,
                pre_reset_energy=round(pre_reset_energy, 6),
                post_reset_energy=round(pre_reset_energy, 6),
                energy_delta=0.0,
                converged=False,
                node_count=len(node_phases),
                safety_lock=True,
            )
        avg_error = sum(phase_errors) / len(phase_errors)
        pre_reset_energy = serotonin_gain * (
            sum(1.0 - math.cos(diff) for diff in phase_diffs) / len(phase_diffs)
        )
        reset_energy = serotonin_gain * (
            sum(math.sin(diff) for diff in phase_diffs) / len(phase_diffs)
        )
        corrected_phase_diffs = [diff - reset_energy for diff in phase_diffs]
        post_reset_energy = serotonin_gain * (
            sum(1.0 - math.cos(diff) for diff in corrected_phase_diffs) / len(corrected_phase_diffs)
        )
        energy_delta = post_reset_energy - pre_reset_energy
        converged = avg_error <= convergence_tol

        return ResetWaveReport(
            activation_trigger="NeuroHomeostaticStabilizer",
            write_ops_inhibited=True,
            average_phase_error=round(avg_error, 6),
            reset_energy=round(reset_energy, 6),
            pre_reset_energy=round(pre_reset_energy, 6),
            post_reset_energy=round(post_reset_energy, 6),
            energy_delta=round(energy_delta, 6),
            converged=converged,
            node_count=len(node_phases),
            safety_lock=False,
        )


def _to_float(v: object) -> float:
    """Safe float — NaN/Inf → 0.0 (fail-closed)."""
    if isinstance(v, (int, float)):
        import math as _m

        f = float(v)
        return f if _m.isfinite(f) else 0.0
    return 0.0


def _gamma_instability(gamma: float) -> float:
    """How far gamma is from metastable point (1.0).

    Returns ∈ [0, 1]: 0 = perfectly metastable, 1 = maximally unstable.
    """
    if not math.isfinite(gamma):
        return 1.0
    return min(1.0, abs(gamma - 1.0))
