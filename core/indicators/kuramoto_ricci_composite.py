from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

import numpy as np
import pandas as pd

from ..utils.logging import get_logger
from .multiscale_kuramoto import MultiScaleKuramoto, MultiScaleResult
from .temporal_ricci import TemporalRicciAnalyzer, TemporalRicciResult
from .volatility import AtrVolatilityAdapter, VolatilityProfile


_logger = get_logger(__name__)


class MarketPhase(Enum):
    CHAOTIC = "chaotic"
    PROTO_EMERGENT = "proto_emergent"
    STRONG_EMERGENT = "strong_emergent"
    TRANSITION = "transition"
    POST_EMERGENT = "post_emergent"


@dataclass
class CompositeSignal:
    phase: MarketPhase
    confidence: float
    kuramoto_R: float
    consensus_R: float
    cross_scale_coherence: float
    static_ricci: float
    temporal_ricci: float
    topological_transition: float
    entry_signal: float
    exit_signal: float
    risk_multiplier: float
    dominant_timeframe_sec: Optional[int]
    timestamp: pd.Timestamp
    skipped_timeframes: list[str] = field(default_factory=list)
    volatility_regime: str = "neutral"
    volatility_score: float = 0.0
    volatility_atr: float = 0.0
    volatility_normalized_atr: float = 0.0


class KuramotoRicciComposite:
    def __init__(
        self,
        R_strong_emergent: float = 0.8,
        R_proto_emergent: float = 0.4,
        coherence_threshold: float = 0.6,
        ricci_negative_threshold: float = -0.3,
        temporal_ricci_threshold: float = -0.2,
        transition_threshold: float = 0.7,
        min_confidence: float = 0.5,
    ) -> None:
        self.Rs = R_strong_emergent
        self.Rp = R_proto_emergent
        self.coh_min = coherence_threshold
        self.kneg = ricci_negative_threshold
        self.kt_thr = temporal_ricci_threshold
        self.trans_thr = transition_threshold
        self.min_conf = min_confidence
        self._volatility_risk_scale = 1.0
        self._volatility_regime = "neutral"
        self._volatility_score = 0.0
        self._volatility_atr = 0.0
        self._volatility_normalized_atr = 0.0

    def set_volatility_context(
        self,
        *,
        risk_scale: float = 1.0,
        regime: str = "neutral",
        regime_score: float = 0.0,
        atr: float = 0.0,
        normalized_atr: float = 0.0,
    ) -> None:
        """Update risk scaling and metadata for the current volatility regime."""

        risk_scale = float(max(risk_scale, 0.05))
        self._volatility_risk_scale = risk_scale
        self._volatility_regime = regime
        self._volatility_score = float(np.clip(regime_score, 0.0, 1.0))
        self._volatility_atr = float(max(atr, 0.0))
        self._volatility_normalized_atr = float(max(normalized_atr, 0.0))

    def _phase(self, R: float, kt: float, trans: float, k_static: float) -> MarketPhase:
        if R > self.Rs and k_static < self.kneg and kt < self.kt_thr and trans < 0.5:
            return MarketPhase.STRONG_EMERGENT
        if trans > self.trans_thr:
            return MarketPhase.TRANSITION
        if self.Rp < R <= self.Rs and trans < 0.5 and k_static < 0:
            return MarketPhase.PROTO_EMERGENT
        if R > self.Rp and (k_static > 0 or kt > 0):
            return MarketPhase.POST_EMERGENT
        return MarketPhase.CHAOTIC

    def _confidence(
        self, phase: MarketPhase, coherence: float, trans: float, R: float
    ) -> float:
        conf = coherence
        if phase == MarketPhase.STRONG_EMERGENT:
            conf *= 1.0 + R
        elif phase == MarketPhase.CHAOTIC:
            conf *= 0.5
        elif phase == MarketPhase.TRANSITION:
            conf *= 0.5 + 0.5 * trans
        dist = min(abs(R - self.Rs), abs(R - self.Rp))
        if dist < 0.1:
            conf *= 0.8
        return float(np.clip(conf, 0.0, 1.0))

    def _entry(self, phase: MarketPhase, R: float, kt: float, conf: float) -> float:
        if conf < self.min_conf:
            return 0.0
        if phase == MarketPhase.STRONG_EMERGENT:
            signal = np.clip(-kt, 0.0, 1.0)
        elif phase == MarketPhase.PROTO_EMERGENT:
            signal = 0.5 * R
        elif phase == MarketPhase.POST_EMERGENT:
            signal = -0.3
        else:
            signal = 0.0
        return float(np.clip(signal * conf, -1.0, 1.0))

    def _exit(self, phase: MarketPhase, trans: float, R: float) -> float:
        if phase == MarketPhase.POST_EMERGENT:
            return 0.7
        if phase == MarketPhase.TRANSITION:
            return float(np.clip(trans, 0.0, 1.0))
        if phase == MarketPhase.CHAOTIC:
            return 0.5
        if phase == MarketPhase.STRONG_EMERGENT:
            return 0.1
        return 0.3

    def _risk(self, phase: MarketPhase, conf: float, coh: float) -> float:
        base = 1.0
        if phase == MarketPhase.STRONG_EMERGENT:
            base = 1.0 + 0.5 * conf
        elif phase == MarketPhase.PROTO_EMERGENT:
            base = 0.7 + 0.3 * conf
        elif phase in (MarketPhase.TRANSITION, MarketPhase.CHAOTIC):
            base = 0.3
        elif phase == MarketPhase.POST_EMERGENT:
            base = 0.2
        scaled = base * coh * self._volatility_risk_scale
        return float(np.clip(scaled, 0.1, 2.0))

    def analyze(
        self,
        kres: MultiScaleResult,
        rres: TemporalRicciResult,
        static_ricci: float,
        ts: pd.Timestamp,
    ) -> CompositeSignal:
        R = float(kres.consensus_R)
        coh = float(kres.cross_scale_coherence)
        kt = float(rres.temporal_curvature)
        trans = float(rres.topological_transition_score)
        phase = self._phase(R, kt, trans, static_ricci)
        conf = self._confidence(phase, coh, trans, R)
        entry = self._entry(phase, R, kt, conf)
        exit_u = self._exit(phase, trans, R)
        risk = self._risk(phase, conf, coh)
        return CompositeSignal(
            phase=phase,
            confidence=conf,
            kuramoto_R=R,
            consensus_R=R,
            cross_scale_coherence=coh,
            static_ricci=static_ricci,
            temporal_ricci=kt,
            topological_transition=trans,
            entry_signal=entry,
            exit_signal=exit_u,
            risk_multiplier=risk,
            dominant_timeframe_sec=(
                kres.dominant_scale.seconds if kres.dominant_scale else None
            ),
            timestamp=ts,
            skipped_timeframes=[str(tf) for tf in kres.skipped_timeframes],
            volatility_regime=self._volatility_regime,
            volatility_score=self._volatility_score,
            volatility_atr=self._volatility_atr,
            volatility_normalized_atr=self._volatility_normalized_atr,
        )

    def to_dict(self, s: CompositeSignal) -> Dict:
        return {
            "timestamp": s.timestamp,
            "phase": s.phase.value,
            "confidence": s.confidence,
            "entry_signal": s.entry_signal,
            "exit_signal": s.exit_signal,
            "risk_multiplier": s.risk_multiplier,
            "kuramoto_R": s.kuramoto_R,
            "consensus_R": s.consensus_R,
            "coherence": s.cross_scale_coherence,
            "static_ricci": s.static_ricci,
            "temporal_ricci": s.temporal_ricci,
            "topological_transition": s.topological_transition,
            "dominant_timeframe_sec": s.dominant_timeframe_sec,
            "skipped_timeframes": s.skipped_timeframes,
            "volatility_regime": s.volatility_regime,
            "volatility_score": s.volatility_score,
            "volatility_atr": s.volatility_atr,
            "volatility_normalized_atr": s.volatility_normalized_atr,
        }

    def _determine_phase(
        self,
        R: float,
        temporal_ricci: float,
        transition_score: float,
        static_ricci: float,
    ) -> MarketPhase:
        return self._phase(R, temporal_ricci, transition_score, static_ricci)

    def _compute_confidence(
        self, phase: MarketPhase, coherence: float, transition_score: float, R: float
    ) -> float:
        return self._confidence(phase, coherence, transition_score, R)

    def _generate_entry_signal(
        self,
        phase: MarketPhase,
        R: float,
        temporal_ricci: float,
        transition_score: float,
        confidence: float,
    ) -> float:
        return self._entry(phase, R, temporal_ricci, confidence)

    def _generate_exit_signal(
        self, phase: MarketPhase, transition_score: float, R: float
    ) -> float:
        return self._exit(phase, transition_score, R)

    def _compute_risk_multiplier(
        self, phase: MarketPhase, confidence: float, coherence: float
    ) -> float:
        return self._risk(phase, confidence, coherence)


@dataclass(frozen=True)
class _CompositeBaselines:
    kuramoto_base_window: int
    kuramoto_min_samples: int
    selector_min_window: int
    selector_max_window: int
    ricci_window_size: int
    ricci_connection_threshold: float
    ricci_shock_sensitivity: float
    ricci_transition_midpoint: float
    composite_Rs: float
    composite_Rp: float
    composite_coherence: float
    composite_kneg: float
    composite_kt_thr: float
    composite_trans_thr: float
    composite_min_conf: float


class TradePulseCompositeEngine:
    def __init__(
        self,
        kuramoto_config: Optional[Dict] = None,
        ricci_config: Optional[Dict] = None,
        composite_config: Optional[Dict] = None,
        *,
        volatility_adapter: Optional[AtrVolatilityAdapter] = None,
    ):
        self.k = MultiScaleKuramoto(**(kuramoto_config or {}))
        self.r = TemporalRicciAnalyzer(**(ricci_config or {}))
        self.c = KuramotoRicciComposite(**(composite_config or {}))
        self.volatility_adapter = volatility_adapter or AtrVolatilityAdapter()
        self._baselines = _CompositeBaselines(
            kuramoto_base_window=self.k.base_window,
            kuramoto_min_samples=self.k.min_samples_per_scale,
            selector_min_window=self.k.selector.min_window,
            selector_max_window=self.k.selector.max_window,
            ricci_window_size=self.r.window_size,
            ricci_connection_threshold=self.r.connection_threshold,
            ricci_shock_sensitivity=self.r.shock_sensitivity,
            ricci_transition_midpoint=self.r.transition_midpoint,
            composite_Rs=self.c.Rs,
            composite_Rp=self.c.Rp,
            composite_coherence=self.c.coh_min,
            composite_kneg=self.c.kneg,
            composite_kt_thr=self.c.kt_thr,
            composite_trans_thr=self.c.trans_thr,
            composite_min_conf=self.c.min_conf,
        )
        self._last_volatility_profile: VolatilityProfile = (
            self.volatility_adapter.neutral_profile()
        )
        self._apply_volatility_profile(self._last_volatility_profile)
        self.history: list[CompositeSignal] = []
        # Track signals by timestamp to guarantee idempotent retries.
        self._history_index: dict[pd.Timestamp, int] = {}

    def analyze_market(
        self,
        df: pd.DataFrame,
        price_col: str = "close",
        volume_col: str = "volume",
        high_col: Optional[str] = "high",
        low_col: Optional[str] = "low",
    ) -> CompositeSignal:
        if self.volatility_adapter is not None:
            try:
                profile = self.volatility_adapter.evaluate(
                    df,
                    price_col=price_col,
                    high_col=high_col,
                    low_col=low_col,
                )
            except Exception as exc:  # pragma: no cover - defensive guardrail
                _logger.warning("volatility adaptation failed; reverting to neutral", exc_info=exc)
                profile = self.volatility_adapter.neutral_profile()
            self._apply_volatility_profile(profile)

        kres = self.k.analyze(df, price_col=price_col)
        rres = self.r.analyze(df, price_col=price_col, volume_col=volume_col)
        static_ricci = (
            rres.graph_snapshots[-1].avg_curvature if rres.graph_snapshots else 0.0
        )
        sig = self.c.analyze(kres, rres, static_ricci, df.index[-1])
        self._record_signal(sig)
        return sig

    @property
    def last_volatility_profile(self) -> VolatilityProfile:
        return self._last_volatility_profile

    def get_signal_dataframe(self) -> pd.DataFrame:
        if not self.history:
            return pd.DataFrame()
        return pd.DataFrame([self.c.to_dict(s) for s in self.history])

    @property
    def signal_history(self) -> list[CompositeSignal]:
        return self.history

    def _record_signal(self, signal: CompositeSignal) -> None:
        """Persist a signal ensuring retries are idempotent."""

        ts = signal.timestamp
        idx = self._history_index.get(ts)
        if idx is not None:
            self.history[idx] = signal
            return

        self.history.append(signal)
        self._history_index[ts] = len(self.history) - 1

    def _apply_volatility_profile(self, profile: VolatilityProfile) -> None:
        self._last_volatility_profile = profile
        base = self._baselines

        window_scale = float(max(profile.smoothing_scale, 0.1))
        threshold_scale = float(max(profile.threshold_scale, 0.1))

        self.k.base_window = _clamp_int(base.kuramoto_base_window * window_scale, minimum=32)
        self.k.min_samples_per_scale = _clamp_int(
            base.kuramoto_min_samples * window_scale,
            minimum=16,
        )
        selector = self.k.selector
        if selector is not None:
            selector.min_window = _clamp_int(
                base.selector_min_window * window_scale,
                minimum=16,
            )
            selector.max_window = max(
                selector.min_window,
                _clamp_int(base.selector_max_window * window_scale, minimum=selector.min_window),
            )
            selector._widths_cache = None  # invalidate cached candidate widths

        self.r.window_size = _clamp_int(base.ricci_window_size * window_scale, minimum=10)
        self.r.connection_threshold = float(
            np.clip(base.ricci_connection_threshold * threshold_scale, 0.01, 1.0)
        )
        self.r.builder.connection_threshold = self.r.connection_threshold
        shock_scale = 1.0 / float(max(threshold_scale, 0.25)) ** 0.5
        self.r.shock_sensitivity = float(
            np.clip(base.ricci_shock_sensitivity * shock_scale, 0.5, 50.0)
        )
        self.r.transition_midpoint = float(
            np.clip(base.ricci_transition_midpoint * threshold_scale, 0.01, 0.95)
        )

        self.c.Rs = float(np.clip(base.composite_Rs * threshold_scale, 0.2, 0.98))
        proto = float(np.clip(base.composite_Rp * threshold_scale, 0.05, 0.95))
        self.c.Rp = min(proto, self.c.Rs - 1e-3)
        self.c.coh_min = float(np.clip(base.composite_coherence * threshold_scale, 0.1, 0.99))
        self.c.kneg = float(base.composite_kneg * threshold_scale)
        self.c.kt_thr = float(base.composite_kt_thr * threshold_scale)
        self.c.trans_thr = float(np.clip(base.composite_trans_thr * threshold_scale, 0.2, 0.95))
        confidence_scale = 1.0 + (threshold_scale - 1.0) * 0.6
        self.c.min_conf = float(np.clip(base.composite_min_conf * confidence_scale, 0.2, 0.95))
        self.c.set_volatility_context(
            risk_scale=profile.risk_scale,
            regime=profile.regime.value,
            regime_score=profile.regime_score,
            atr=profile.atr,
            normalized_atr=profile.normalized_atr,
        )


def _clamp_int(value: float, *, minimum: int, maximum: Optional[int] = None) -> int:
    rounded = int(round(value))
    if rounded < minimum:
        rounded = minimum
    if maximum is not None and rounded > maximum:
        rounded = maximum
    return rounded
