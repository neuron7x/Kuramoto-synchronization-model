"""MetaCognition Layer — система бачить себе (model-level self-monitoring).

CNS doesn't just process signals — it monitors its own processing.
Prefrontal cortex observes how other regions make decisions.

GeoSyncDecisionEngine observes the market.
MetaCognitionLayer observes GeoSyncDecisionEngine.

Subsystems (computational analogy, NOT functional homology — see SCOPE below):
  1. PredictionErrorMonitor   — analogue: prefrontal prediction vs outcome
  2. CalibrationDriftDetector — analogue: cerebellum decision-distribution drift
  3. ModelGammaEstimator      — analogue: interoception γ₂ of the model itself
  4. IndependentWitness       — analogue: ACC error detection / blind-spot guard
  5. MetaCognitionLayer       — unified gate: all four → MetaState

Key invariant:
  γ₂ (model) ≈ γ (market) → model is in resonance with market
  γ₂ ≠ γ     → model is in a different regime → OBSERVE

⚠️ SCOPE OF BIO-NAMING.
The four sub-blocks are decision-rate moving averages with empirically chosen
constants (e.g. ``ModelGammaEstimator`` derives γ_model from
``var − 0.125`` × 8.0 — a calibration-anchor, not a neuroanatomical mapping).
The "prefrontal / cerebellum / interoception / ACC" labels are analogical
shorthand for *what* each block monitors, not a claim that the implementation
reproduces the cellular mechanisms of those regions. The block boundaries are
useful for product reasoning (each block falsifies a distinct mode of model
failure) but are not load-bearing physics. For the genuine neuroanatomy map
of GeoSync, see ``~/CANONICAL_NEURO_MAPPING_2026_05_05.md``.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModelRegime(Enum):
    RESONANT = "RESONANT"
    LAGGING = "LAGGING"
    OVERFIT = "OVERFIT"
    DRIFTING = "DRIFTING"
    BLIND_SPOT = "BLIND_SPOT"


@dataclass(frozen=True, slots=True)
class PredictionError:
    expected_regime: str
    actual_regime: str
    confidence_at_prediction: float
    error_magnitude: float
    is_overconfident: bool
    surprise_bits: float


@dataclass(frozen=True, slots=True)
class CalibrationSnapshot:
    trade_rate: float
    observe_rate: float
    abort_rate: float
    drift_score: float
    is_paralyzed: bool
    is_reckless: bool


@dataclass(frozen=True, slots=True)
class ModelGamma:
    gamma_model: float
    gamma_market: float
    resonance: float
    is_resonant: bool


@dataclass(frozen=True, slots=True)
class MetaState:
    model_regime: ModelRegime
    gamma_model: ModelGamma
    calibration: CalibrationSnapshot
    last_prediction_error: PredictionError | None
    meta_confidence: float
    kelly_meta_multiplier: float
    should_recalibrate: bool
    cumulative_error: float
    blind_spot_regime: str | None
    witness_alert: bool
    witness_reason: str


class PredictionErrorMonitor:
    """Tracks gap between model's predictions and actual outcomes."""

    def __init__(self, window: int = 50) -> None:
        self._pending: dict[str, tuple[str, float]] = {}
        self._errors: deque[float] = deque(maxlen=window)
        self._overconfident_count: int = 0
        self._total_count: int = 0

    def record_prediction(self, instrument: str, predicted_next: str, confidence: float) -> None:
        self._pending[instrument] = (predicted_next, confidence)

    def observe_outcome(self, instrument: str, actual_regime: str) -> PredictionError | None:
        if instrument not in self._pending:
            return None

        predicted, confidence = self._pending.pop(instrument)
        self._total_count += 1
        is_wrong = predicted != actual_regime

        error_mag = confidence if is_wrong else 0.0

        if is_wrong:
            surprise = -math.log2(max(1e-6, 1.0 - confidence))
        else:
            surprise = max(0.0, -math.log2(max(1e-6, confidence)))

        is_overconfident = is_wrong and confidence > 0.7
        if is_overconfident:
            self._overconfident_count += 1

        self._errors.append(error_mag)

        return PredictionError(
            expected_regime=predicted,
            actual_regime=actual_regime,
            confidence_at_prediction=confidence,
            error_magnitude=round(error_mag, 4),
            is_overconfident=is_overconfident,
            surprise_bits=round(surprise, 4),
        )

    @property
    def rolling_mean_error(self) -> float:
        if not self._errors:
            return 0.5
        return sum(self._errors) / len(self._errors)

    @property
    def overconfidence_rate(self) -> float:
        if self._total_count == 0:
            return 0.0
        return self._overconfident_count / self._total_count


class CalibrationDriftDetector:
    """Monitors TRADE/OBSERVE/ABORT distribution for drift."""

    TARGET = {"TRADE": 0.47, "OBSERVE": 0.37, "ABORT": 0.16}
    PARALYSIS_THRESHOLD = 0.10
    RECKLESS_THRESHOLD = 0.80
    DRIFT_ALERT_THRESHOLD = 0.25

    def __init__(self, window: int = 200) -> None:
        self._decisions: deque[str] = deque(maxlen=window)

    def record(self, decision: str) -> None:
        self._decisions.append(decision)

    def snapshot(self) -> CalibrationSnapshot:
        if len(self._decisions) < 20:
            return CalibrationSnapshot(
                trade_rate=0.47,
                observe_rate=0.37,
                abort_rate=0.16,
                drift_score=0.0,
                is_paralyzed=False,
                is_reckless=False,
            )

        total = len(self._decisions)
        counts = {"TRADE": 0, "OBSERVE": 0, "ABORT": 0}
        for d in self._decisions:
            if d in counts:
                counts[d] += 1

        trade_r = counts["TRADE"] / total
        observe_r = counts["OBSERVE"] / total
        abort_r = counts["ABORT"] / total

        drift = (
            abs(trade_r - self.TARGET["TRADE"])
            + abs(observe_r - self.TARGET["OBSERVE"])
            + abs(abort_r - self.TARGET["ABORT"])
        ) / 2.0

        return CalibrationSnapshot(
            trade_rate=round(trade_r, 4),
            observe_rate=round(observe_r, 4),
            abort_rate=round(abort_r, 4),
            drift_score=round(drift, 4),
            is_paralyzed=trade_r < self.PARALYSIS_THRESHOLD,
            is_reckless=trade_r > self.RECKLESS_THRESHOLD,
        )


class ModelGammaEstimator:
    """Estimates γ₂: the model's own gamma from decision variance."""

    RESONANCE_THRESHOLD = 0.75

    def __init__(self, window: int = 100) -> None:
        self._decision_vals: deque[float] = deque(maxlen=window)
        self._encoding = {"TRADE": 1.0, "OBSERVE": 0.5, "ABORT": 0.0}

    def record_decision(self, decision: str) -> None:
        self._decision_vals.append(self._encoding.get(decision, 0.5))

    def estimate(self, gamma_market: float) -> ModelGamma:
        if len(self._decision_vals) < 20:
            return ModelGamma(
                gamma_model=1.0,
                gamma_market=gamma_market,
                resonance=0.5,
                is_resonant=False,
            )

        vals = list(self._decision_vals)
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)

        gamma_model = 1.0 + (var - 0.125) * 8.0
        gamma_model = max(0.1, min(3.0, gamma_model))

        dist = abs(gamma_model - gamma_market)
        resonance = max(0.0, 1.0 - dist / 2.0)

        return ModelGamma(
            gamma_model=round(gamma_model, 4),
            gamma_market=round(gamma_market, 4),
            resonance=round(resonance, 4),
            is_resonant=resonance > self.RESONANCE_THRESHOLD,
        )


class IndependentWitness:
    """ACC analog: detects conflict and error independently."""

    def __init__(self) -> None:
        self._regime_errors: dict[str, list[float]] = {}

    def record_error(self, regime: str, error: float) -> None:
        if regime not in self._regime_errors:
            self._regime_errors[regime] = []
        errs = self._regime_errors[regime]
        errs.append(error)
        if len(errs) > 50:
            self._regime_errors[regime] = errs[-50:]

    def detect_blind_spot(self) -> str | None:
        worst_regime = None
        worst_error = 0.4

        for regime, errors in self._regime_errors.items():
            if len(errors) < 5:
                continue
            mean_err = sum(errors) / len(errors)
            if mean_err > worst_error:
                worst_error = mean_err
                worst_regime = regime

        return worst_regime

    def assess(
        self,
        calibration: CalibrationSnapshot,
        gamma_model: ModelGamma,
        overconfidence_rate: float,
        cumulative_error: float,
    ) -> tuple[bool, str]:
        if calibration.is_paralyzed:
            return True, f"PARALYSIS: TRADE rate {calibration.trade_rate:.0%} < 10%"
        if calibration.is_reckless:
            return True, f"RECKLESS: TRADE rate {calibration.trade_rate:.0%} > 80%"
        if calibration.drift_score > CalibrationDriftDetector.DRIFT_ALERT_THRESHOLD:
            return True, f"CALIBRATION DRIFT: L1={calibration.drift_score:.3f}"
        if overconfidence_rate > 0.30:
            return True, f"OVERCONFIDENCE: {overconfidence_rate:.0%} high-conf misses"
        if not gamma_model.is_resonant:
            return True, (
                f"RESONANCE BREAK: γ₂={gamma_model.gamma_model:.3f}"
                f" ≠ γ={gamma_model.gamma_market:.3f}"
            )
        blind = self.detect_blind_spot()
        if blind:
            return True, f"BLIND SPOT in {blind}"
        if cumulative_error > 0.5:
            return True, f"CUMULATIVE ERROR: {cumulative_error:.3f} > 0.5"
        return False, "OK"


class MetaCognitionLayer:
    """System that observes itself. Sits above DecisionEngine."""

    def __init__(
        self,
        *,
        error_window: int = 50,
        calibration_window: int = 200,
        gamma_window: int = 100,
    ) -> None:
        self._pred = PredictionErrorMonitor(window=error_window)
        self._cal = CalibrationDriftDetector(window=calibration_window)
        self._gamma = ModelGammaEstimator(window=gamma_window)
        self._witness = IndependentWitness()

    def observe(
        self,
        signal: dict[str, Any],
        decision_output: Any,
        regime_memory: Any,
    ) -> MetaState:
        instrument = str(signal.get("instrument", "UNKNOWN"))
        actual_regime = str(signal.get("regime", "UNKNOWN"))
        gamma_market = _f(signal.get("gamma", 1.0))
        confidence = _f(signal.get("regime_confidence", 0.5))
        decision_str = decision_output.decision.value

        pred_error = self._pred.observe_outcome(instrument, actual_regime)
        if pred_error and pred_error.error_magnitude > 0:
            self._witness.record_error(actual_regime, pred_error.error_magnitude)

        expected_next = _get_expected(regime_memory, instrument)
        self._pred.record_prediction(instrument, expected_next, confidence)

        self._cal.record(decision_str)
        calibration = self._cal.snapshot()

        self._gamma.record_decision(decision_str)
        gamma_model = self._gamma.estimate(gamma_market)

        cumulative_error = self._pred.rolling_mean_error
        overconf_rate = self._pred.overconfidence_rate

        witness_alert, witness_reason = self._witness.assess(
            calibration,
            gamma_model,
            overconf_rate,
            cumulative_error,
        )

        model_regime = _classify(gamma_model, calibration, witness_alert)
        meta_confidence = _meta_conf(
            gamma_model,
            calibration,
            cumulative_error,
            witness_alert,
        )

        return MetaState(
            model_regime=model_regime,
            gamma_model=gamma_model,
            calibration=calibration,
            last_prediction_error=pred_error,
            meta_confidence=round(meta_confidence, 4),
            kelly_meta_multiplier=round(max(0.1, meta_confidence), 4),
            should_recalibrate=calibration.drift_score > 0.35 or witness_alert,
            cumulative_error=round(cumulative_error, 4),
            blind_spot_regime=self._witness.detect_blind_spot(),
            witness_alert=witness_alert,
            witness_reason=witness_reason,
        )

    def get_meta_features(self, meta_state: MetaState) -> dict[str, float]:
        """6 metacognitive features for RF meta-labeler."""
        return {
            "gamma_model": meta_state.gamma_model.gamma_model,
            "gamma_resonance": meta_state.gamma_model.resonance,
            "calibration_drift": meta_state.calibration.drift_score,
            "cumulative_pred_error": meta_state.cumulative_error,
            "meta_confidence": meta_state.meta_confidence,
            "witness_alert": float(meta_state.witness_alert),
        }


def _f(v: object) -> float:
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else 0.0
    return 0.0


def _get_expected(regime_memory: Any, instrument: str) -> str:
    try:
        r = regime_memory.get_expected_next(instrument)
        return r if isinstance(r, str) else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _classify(
    gm: ModelGamma,
    cal: CalibrationSnapshot,
    witness: bool,
) -> ModelRegime:
    if cal.is_paralyzed:
        return ModelRegime.BLIND_SPOT
    if cal.is_reckless:
        return ModelRegime.OVERFIT
    if cal.drift_score > CalibrationDriftDetector.DRIFT_ALERT_THRESHOLD:
        return ModelRegime.DRIFTING
    if not gm.is_resonant:
        return ModelRegime.LAGGING
    return ModelRegime.RESONANT


def _meta_conf(
    gm: ModelGamma,
    cal: CalibrationSnapshot,
    cum_err: float,
    witness: bool,
) -> float:
    score = 1.0
    score *= 0.5 + 0.5 * gm.resonance
    score *= max(0.3, 1.0 - cal.drift_score * 2.0)
    score *= max(0.2, 1.0 - cum_err)
    if witness:
        score *= 0.4
    return max(0.1, min(1.0, score))
