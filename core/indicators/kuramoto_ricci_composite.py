"""Kuramoto-Ricci composite market phase analyzer.

This module provides a sophisticated market regime classification system that combines
Kuramoto synchronization analysis with Ricci flow curvature metrics to identify
distinct market phases and generate actionable trading signals.

The composite engine fuses multi-scale Kuramoto oscillator analysis with temporal
Ricci flow to classify markets into five distinct phases:
- CHAOTIC: Low synchronization, unpredictable dynamics
- PROTO_EMERGENT: Early synchronization signals appearing
- STRONG_EMERGENT: High synchronization with favorable geometry
- TRANSITION: Phase shift in progress
- POST_EMERGENT: Synchronization breaking down

Key Components:
    MarketPhase: Enumeration of market regime states
    CompositeSignal: Complete signal output with phase, confidence, and trading signals
    KuramotoRicciComposite: Core analyzer that produces signals from raw metrics
    TradePulseCompositeEngine: High-level API for market analysis

Example:
    >>> engine = TradePulseCompositeEngine()
    >>> signal = engine.analyze_market(price_df)
    >>> print(f"Phase: {signal.phase.value}, Entry: {signal.entry_signal}")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .multiscale_kuramoto import MultiScaleKuramoto, MultiScaleResult
from .temporal_ricci import TemporalRicciAnalyzer, TemporalRicciResult


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
    ):
        self.Rs = R_strong_emergent
        self.Rp = R_proto_emergent
        self.coh_min = coherence_threshold
        self.kneg = ricci_negative_threshold
        self.kt_thr = temporal_ricci_threshold
        self.trans_thr = transition_threshold
        self.min_conf = min_confidence

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
        # penalize near thresholds
        dist = min(abs(R - self.Rs), abs(R - self.Rp))
        if dist < 0.1:
            conf *= 0.8
        return float(np.clip(conf, 0.0, 1.0))

    def _entry(self, phase: MarketPhase, R: float, kt: float, conf: float) -> float:
        if conf < self.min_conf:
            return 0.0
        s = 0.0
        if phase == MarketPhase.STRONG_EMERGENT:
            s = np.clip(-kt, 0.0, 1.0)  # more negative -> stronger long
        elif phase == MarketPhase.PROTO_EMERGENT:
            s = 0.5 * R
        elif phase == MarketPhase.POST_EMERGENT:
            s = -0.3
        else:
            s = 0.0
        return float(np.clip(s * conf, -1.0, 1.0))

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
        return float(np.clip(base * coh, 0.1, 2.0))

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
        }

    # Backwards-compatible wrappers for legacy API expectations
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


class TradePulseCompositeEngine:
    def __init__(
        self,
        kuramoto_config: Optional[Dict] = None,
        ricci_config: Optional[Dict] = None,
        composite_config: Optional[Dict] = None,
    ):
        self.k = MultiScaleKuramoto(**(kuramoto_config or {}))
        self.r = TemporalRicciAnalyzer(**(ricci_config or {}))
        self.c = KuramotoRicciComposite(**(composite_config or {}))
        self.history: list[CompositeSignal] = []
        # Track signals by timestamp to guarantee idempotent retries.
        self._history_index: dict[pd.Timestamp, int] = {}

    def _clear_history(self) -> None:
        self.history.clear()
        self._history_index.clear()

    def analyze_market(
        self, df: pd.DataFrame, price_col: str = "close", volume_col: str = "volume"
    ) -> CompositeSignal:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise TypeError("TradePulseCompositeEngine requires a DatetimeIndex")

        sanitized = df.sort_index()
        if sanitized.index.has_duplicates:
            sanitized = sanitized[~sanitized.index.duplicated(keep="last")]

        if sanitized.empty:
            raise ValueError(
                "DataFrame must contain at least one row after sanitisation"
            )

        latest_ts = sanitized.index[-1]
        last_signal: CompositeSignal | None = self.history[-1] if self.history else None

        should_reset_history = False
        if last_signal is not None:
            last_ts = last_signal.timestamp
            if latest_ts == last_ts:
                return last_signal
            reset_temporal = sanitized.index[0] <= last_ts
            if latest_ts < last_ts:
                should_reset_history = True
                last_signal = None
                reset_temporal = True
        else:
            reset_temporal = False

        kres = self.k.analyze(sanitized, price_col=price_col)
        rres = self.r.analyze(
            sanitized,
            price_col=price_col,
            volume_col=volume_col,
            reset_history=reset_temporal,
        )
        static_ricci = (
            rres.graph_snapshots[-1].avg_curvature if rres.graph_snapshots else 0.0
        )
        sig = self.c.analyze(kres, rres, static_ricci, sanitized.index[-1])
        if should_reset_history:
            self._clear_history()
        self._record_signal(sig)
        return sig

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
