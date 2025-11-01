# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
    from hypothesis.extra.numpy import arrays
except Exception:  # pragma: no cover - optional dependency
    HYPOTHESIS_AVAILABLE = False
else:  # pragma: no branch
    HYPOTHESIS_AVAILABLE = True

from core.indicators import (
    KuramotoRicciComposite,
    MarketPhase,
    MultiScaleKuramoto,
    MultiScaleResult,
    TemporalRicciAnalyzer,
    TimeFrame,
    TradePulseCompositeEngine,
    WaveletWindowSelector,
)
from core.indicators.kuramoto_ricci_composite import CompositeSignal
from core.indicators.temporal_ricci import (
    GraphSnapshot,
    LightGraph,
    OllivierRicciCurvature,
    TemporalRicciResult,
)


class TestMultiScaleKuramoto:
    def test_kuramoto_order_parameter_bounds(self) -> None:
        analyzer = MultiScaleKuramoto(use_adaptive_window=False)
        phases = np.random.uniform(-np.pi, np.pi, 128)
        R, psi = analyzer._kuramoto_order_parameter(phases)
        assert 0.0 <= R <= 1.0
        assert -np.pi <= psi <= np.pi

    def test_perfect_synchronisation(self) -> None:
        analyzer = MultiScaleKuramoto(use_adaptive_window=False)
        phases = np.ones(64) * (np.pi / 4.0)
        R, _ = analyzer._kuramoto_order_parameter(phases)
        assert R > 0.99

    def test_random_phases_low_R(self) -> None:
        analyzer = MultiScaleKuramoto(use_adaptive_window=False)
        rng = np.random.default_rng(42)
        phases = rng.uniform(-np.pi, np.pi, 2048)
        R, _ = analyzer._kuramoto_order_parameter(phases)
        assert R < 0.2

    def test_adaptive_window_selection(self) -> None:
        selector = WaveletWindowSelector(min_window=50, max_window=200)
        t = np.arange(512)
        prices = 100 + 5 * np.sin(2 * np.pi * t / 64)
        window = selector.select_window(prices)
        assert 50 <= window <= 200

    def test_multiscale_consensus(self) -> None:
        dates = pd.date_range("2024-01-01", periods=512, freq="1min")
        t = np.arange(len(dates))
        prices = 100 + np.sin(2 * np.pi * t / 50) + 0.3 * np.sin(2 * np.pi * t / 120)
        df = pd.DataFrame({"close": prices}, index=dates)

        analyzer = MultiScaleKuramoto(use_adaptive_window=False, base_window=64)
        result = analyzer.analyze(df)
        assert 0.0 <= result.consensus_R <= 1.0
        assert 0.0 <= result.cross_scale_coherence <= 1.0
        assert result.dominant_scale in TimeFrame

    if HYPOTHESIS_AVAILABLE:

        @settings(max_examples=5, deadline=None)
        @given(
            prices=arrays(
                dtype=np.float64,
                shape=st.integers(min_value=200, max_value=600),
                elements=st.floats(min_value=50.0, max_value=150.0, allow_nan=False),
            )
        )
        def test_kuramoto_robustness(self, prices: np.ndarray) -> None:
            dates = pd.date_range("2024-01-01", periods=len(prices), freq="1min")
            df = pd.DataFrame({"close": prices}, index=dates)
            analyzer = MultiScaleKuramoto(use_adaptive_window=False, base_window=64)
            result = analyzer.analyze(df)
            assert 0.0 <= result.consensus_R <= 1.0
            assert not np.isnan(result.consensus_R)

    else:  # pragma: no cover - executed when Hypothesis missing

        def test_kuramoto_robustness(self) -> None:  # type: ignore[override]
            pytest.skip("hypothesis not installed")


class TestTemporalRicci:
    def test_ollivier_ricci_symmetry(self) -> None:
        nx = pytest.importorskip("networkx")

        G = nx.complete_graph(5)
        calculator = OllivierRicciCurvature(alpha=0.5)
        for edge in G.edges():
            x, y = edge
            kappa_xy = calculator.compute_edge_curvature(G, (x, y))
            kappa_yx = calculator.compute_edge_curvature(G, (y, x))
            assert abs(kappa_xy - kappa_yx) < 1e-10

    def test_complete_graph_positive_curvature(self) -> None:
        nx = pytest.importorskip("networkx")

        G = nx.complete_graph(8)
        calculator = OllivierRicciCurvature()
        curvatures = calculator.compute_all_curvatures(G)
        assert np.mean(list(curvatures.values())) > 0

    def test_temporal_ricci_detects_regime_change(self) -> None:
        dates = pd.date_range("2024-01-01", periods=800, freq="1min")
        rng = np.random.default_rng(123)
        stable = 100 + np.cumsum(rng.normal(0, 0.05, 400))
        volatile = stable[-1] + np.cumsum(rng.normal(0, 0.8, 400))
        prices = np.concatenate([stable, volatile])
        volumes = rng.lognormal(mean=7, sigma=0.5, size=len(prices))
        df = pd.DataFrame({"close": prices, "volume": volumes}, index=dates)

        analyzer = TemporalRicciAnalyzer(window_size=80, n_snapshots=8)
        result = analyzer.analyze(df)
        assert result.topological_transition_score > 0.3

    def test_stable_market_high_stability(self) -> None:
        dates = pd.date_range("2024-01-01", periods=600, freq="1min")
        rng = np.random.default_rng(321)
        prices = 100 + 0.01 * np.arange(len(dates)) + rng.normal(0, 0.05, len(dates))
        volumes = np.full(len(dates), 1000.0)
        df = pd.DataFrame({"close": prices, "volume": volumes}, index=dates)

        analyzer = TemporalRicciAnalyzer(window_size=80, n_snapshots=6)
        result = analyzer.analyze(df)
        assert result.structural_stability > 0.35


class TestCompositeIndicator:
    def test_phase_detection_strong_emergent(self) -> None:
        composite = KuramotoRicciComposite(
            R_strong_emergent=0.8, ricci_negative_threshold=-0.3
        )
        phase = composite._determine_phase(
            R=0.85,
            temporal_ricci=-0.25,
            transition_score=0.3,
            static_ricci=-0.4,
        )
        assert phase is MarketPhase.STRONG_EMERGENT

    def test_phase_detection_transition(self) -> None:
        composite = KuramotoRicciComposite()
        phase = composite._determine_phase(
            R=0.6,
            temporal_ricci=-0.1,
            transition_score=0.8,
            static_ricci=-0.2,
        )
        assert phase is MarketPhase.TRANSITION

    def test_phase_detection_proto_emergent_branch(self) -> None:
        composite = KuramotoRicciComposite(R_proto_emergent=0.4, R_strong_emergent=0.8)
        phase = composite._determine_phase(
            R=0.55,
            temporal_ricci=-0.05,
            transition_score=0.2,
            static_ricci=-0.1,
        )
        assert phase is MarketPhase.PROTO_EMERGENT

    def test_phase_detection_post_emergent_branch(self) -> None:
        composite = KuramotoRicciComposite(R_proto_emergent=0.4)
        phase = composite._determine_phase(
            R=0.65,
            temporal_ricci=0.15,
            transition_score=0.3,
            static_ricci=0.1,
        )
        assert phase is MarketPhase.POST_EMERGENT

    def test_phase_detection_defaults_to_chaotic(self) -> None:
        composite = KuramotoRicciComposite(R_proto_emergent=0.4, R_strong_emergent=0.8)
        phase = composite._determine_phase(
            R=0.2,
            temporal_ricci=0.0,
            transition_score=0.1,
            static_ricci=-0.05,
        )
        assert phase is MarketPhase.CHAOTIC

    def test_confidence_range(self) -> None:
        composite = KuramotoRicciComposite()
        confidence = composite._compute_confidence(
            phase=MarketPhase.STRONG_EMERGENT,
            coherence=0.8,
            transition_score=0.2,
            R=0.9,
        )
        assert 0.0 <= confidence <= 1.0

    def test_confidence_penalised_near_threshold(self) -> None:
        composite = KuramotoRicciComposite(R_proto_emergent=0.4, R_strong_emergent=0.8)
        confidence = composite._compute_confidence(
            phase=MarketPhase.STRONG_EMERGENT,
            coherence=0.65,
            transition_score=0.1,
            R=0.82,
        )
        assert confidence == pytest.approx(0.9464, rel=1e-6)

    def test_entry_signal_range(self) -> None:
        composite = KuramotoRicciComposite()
        signal = composite._generate_entry_signal(
            phase=MarketPhase.STRONG_EMERGENT,
            R=0.9,
            temporal_ricci=-0.4,
            transition_score=0.2,
            confidence=0.8,
        )
        assert -1.0 <= signal <= 1.0

    def test_post_emergent_entry_signal_biases_short(self) -> None:
        composite = KuramotoRicciComposite()
        signal = composite._generate_entry_signal(
            phase=MarketPhase.POST_EMERGENT,
            R=0.7,
            temporal_ricci=0.2,
            transition_score=0.3,
            confidence=0.9,
        )
        assert signal < 0

    def test_exit_signal_range(self) -> None:
        composite = KuramotoRicciComposite()
        signal = composite._generate_exit_signal(
            phase=MarketPhase.POST_EMERGENT,
            transition_score=0.6,
            R=0.5,
        )
        assert 0.0 <= signal <= 1.0

    def test_risk_multiplier_range(self) -> None:
        composite = KuramotoRicciComposite()
        multiplier = composite._compute_risk_multiplier(
            phase=MarketPhase.STRONG_EMERGENT,
            confidence=0.9,
            coherence=0.8,
        )
        assert 0.1 <= multiplier <= 2.0

    def test_low_confidence_zero_entry(self) -> None:
        composite = KuramotoRicciComposite(min_confidence=0.5)
        signal = composite._generate_entry_signal(
            phase=MarketPhase.STRONG_EMERGENT,
            R=0.9,
            temporal_ricci=-0.4,
            transition_score=0.2,
            confidence=0.3,
        )
        assert abs(signal) < 0.1

    def test_analyze_serialises_skipped_timeframes(self) -> None:
        composite = KuramotoRicciComposite(
            R_strong_emergent=0.8,
            R_proto_emergent=0.4,
            coherence_threshold=0.6,
            ricci_negative_threshold=-0.2,
            temporal_ricci_threshold=-0.1,
            transition_threshold=0.7,
        )

        multi_result = MultiScaleResult(
            consensus_R=0.85,
            cross_scale_coherence=0.9,
            dominant_scale=TimeFrame.M15,
            adaptive_window=128,
            timeframe_results={},
            skipped_timeframes=[TimeFrame.M1, TimeFrame.M5],
            timeframe_endpoints={},
            timeframe_series={},
            energy_profile={},
        )

        graph = LightGraph(3)
        graph.add_edge(0, 1, weight=1.0)
        snapshot = GraphSnapshot(
            graph=graph,
            timestamp=pd.Timestamp("2024-01-01T12:00:00Z"),
            price_levels=np.array([99.5, 100.0, 100.5]),
            ricci_curvatures={(0, 1): -0.1},
            avg_curvature=-0.1,
        )

        temporal_result = TemporalRicciResult(
            temporal_curvature=-0.2,
            topological_transition_score=0.4,
            graph_snapshots=[snapshot],
            structural_stability=0.8,
            edge_persistence=0.7,
        )

        signal = composite.analyze(
            kres=multi_result,
            rres=temporal_result,
            static_ricci=-0.1,
            ts=pd.Timestamp("2024-01-01T12:00:00Z"),
        )

        assert signal.dominant_timeframe_sec == TimeFrame.M15.seconds
        assert signal.skipped_timeframes == ["M1", "M5"]
        assert signal.phase in MarketPhase

        serialised = composite.to_dict(signal)
        assert serialised["phase"] == signal.phase.value
        assert serialised["dominant_timeframe_sec"] == TimeFrame.M15.seconds
        assert serialised["skipped_timeframes"] == ["M1", "M5"]


class TestCompositeEngine:
    def test_full_pipeline(self) -> None:
        dates = pd.date_range("2024-01-01", periods=600, freq="1min")
        rng = np.random.default_rng(987)
        t = np.arange(len(dates))
        prices = 100 + 3 * np.sin(2 * np.pi * t / 150) + rng.normal(0, 0.4, len(dates))
        volumes = rng.lognormal(mean=7, sigma=0.6, size=len(dates))
        df = pd.DataFrame({"close": prices, "volume": volumes}, index=dates)

        engine = TradePulseCompositeEngine()
        signal = engine.analyze_market(df)

        assert signal.phase in MarketPhase
        assert 0.0 <= signal.confidence <= 1.0
        assert -1.0 <= signal.entry_signal <= 1.0
        assert 0.0 <= signal.exit_signal <= 1.0
        assert 0.1 <= signal.risk_multiplier <= 2.0
        assert not np.isnan(signal.kuramoto_R)
        assert not np.isnan(signal.temporal_ricci)

    def test_signal_history_idempotent_retries(self) -> None:
        dates = pd.date_range("2024-01-01", periods=300, freq="1min")
        rng = np.random.default_rng(654)
        prices = 100 + rng.normal(0, 0.5, len(dates))
        volumes = np.full(len(dates), 1000.0)
        df = pd.DataFrame({"close": prices, "volume": volumes}, index=dates)

        engine = TradePulseCompositeEngine()
        engine.analyze_market(df)
        engine.analyze_market(df)

        assert len(engine.signal_history) == 1
        df_signals = engine.get_signal_dataframe()
        assert len(df_signals) == 1
        assert set(["phase", "entry_signal"]).issubset(df_signals.columns)
        assert pd.Timestamp(df_signals.iloc[0]["timestamp"]) == df.index[-1]

    def test_signal_history_appends_newer_data(self) -> None:
        dates = pd.date_range("2024-01-01", periods=300, freq="1min")
        rng = np.random.default_rng(321)
        prices = 100 + rng.normal(0, 0.5, len(dates))
        volumes = np.full(len(dates), 1000.0)
        df = pd.DataFrame({"close": prices, "volume": volumes}, index=dates)

        engine = TradePulseCompositeEngine()
        engine.analyze_market(df)
        engine.analyze_market(df)  # retry with identical payload should not duplicate

        extended_index = df.index.append(
            pd.Index([df.index[-1] + pd.Timedelta(minutes=1)])
        )
        extended_prices = np.append(prices, prices[-1] + 0.1)
        extended_volumes = np.append(volumes, volumes[-1])
        df_extended = pd.DataFrame(
            {"close": extended_prices, "volume": extended_volumes}, index=extended_index
        )

        engine.analyze_market(df_extended)

        assert len(engine.signal_history) == 2
        assert engine.signal_history[-1].timestamp == df_extended.index[-1]
        df_signals = engine.get_signal_dataframe()
        assert len(df_signals) == 2

    def test_analyze_market_replay_returns_cached_signal(self) -> None:
        dates = pd.date_range("2024-01-01", periods=300, freq="1min")
        rng = np.random.default_rng(777)
        prices = 150 + rng.normal(0, 0.4, len(dates))
        volumes = np.full(len(dates), 500.0)
        df = pd.DataFrame({"close": prices, "volume": volumes}, index=dates)

        engine = TradePulseCompositeEngine()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            first = engine.analyze_market(df)
            second = engine.analyze_market(df)

        assert second is first
        assert len(engine.signal_history) == 1
        assert engine.signal_history[0].timestamp == df.index[-1]
        runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        assert runtime_warnings == []

    def test_analyze_market_backwards_resets_state(self) -> None:
        dates = pd.date_range("2024-01-01", periods=360, freq="1min")
        rng = np.random.default_rng(123)
        prices = 110 + rng.normal(0, 0.6, len(dates))
        volumes = rng.lognormal(mean=7.2, sigma=0.4, size=len(dates))
        df = pd.DataFrame({"close": prices, "volume": volumes}, index=dates)

        engine = TradePulseCompositeEngine()
        recent_signal = engine.analyze_market(df)
        assert recent_signal.timestamp == df.index[-1]
        assert len(engine.signal_history) == 1

        earlier_df = df.iloc[:200]
        backfilled = engine.analyze_market(earlier_df)

        assert len(engine.signal_history) == 1
        assert engine.signal_history[0].timestamp == earlier_df.index[-1]
        assert backfilled.timestamp == earlier_df.index[-1]
        assert engine.r.history
        assert engine.r.history[-1].timestamp <= earlier_df.index[-1]

    def test_get_signal_dataframe_empty_history(self) -> None:
        engine = TradePulseCompositeEngine()
        df = engine.get_signal_dataframe()
        assert df.empty
        assert list(df.columns) == []

    def test_record_signal_overwrites_same_timestamp(self) -> None:
        engine = TradePulseCompositeEngine()
        ts = pd.Timestamp("2024-01-01T00:00:00Z")
        first = CompositeSignal(
            phase=MarketPhase.CHAOTIC,
            confidence=0.3,
            kuramoto_R=0.2,
            consensus_R=0.2,
            cross_scale_coherence=0.4,
            static_ricci=0.05,
            temporal_ricci=0.1,
            topological_transition=0.2,
            entry_signal=-0.1,
            exit_signal=0.5,
            risk_multiplier=0.4,
            dominant_timeframe_sec=None,
            timestamp=ts,
        )
        engine._record_signal(first)

        updated = CompositeSignal(
            phase=MarketPhase.STRONG_EMERGENT,
            confidence=0.9,
            kuramoto_R=0.95,
            consensus_R=0.95,
            cross_scale_coherence=0.92,
            static_ricci=-0.3,
            temporal_ricci=-0.4,
            topological_transition=0.1,
            entry_signal=0.8,
            exit_signal=0.2,
            risk_multiplier=1.5,
            dominant_timeframe_sec=TimeFrame.M5.seconds,
            timestamp=ts,
        )
        engine._record_signal(updated)

        assert len(engine.signal_history) == 1
        stored = engine.signal_history[0]
        assert stored.phase is MarketPhase.STRONG_EMERGENT
        assert stored.entry_signal == pytest.approx(0.8)
        assert stored.risk_multiplier == pytest.approx(1.5)


if HYPOTHESIS_AVAILABLE:

    @st.composite
    def _synthetic_series(draw: st.DrawFn) -> np.ndarray:
        n_points = draw(st.integers(min_value=200, max_value=600))
        volatility = draw(st.floats(min_value=0.01, max_value=2.0))
        rng = np.random.default_rng(draw(st.integers(min_value=0, max_value=10_000)))
        return 100 + np.cumsum(rng.normal(0, volatility, n_points))

    class TestPropertyBased:
        @settings(max_examples=5, deadline=None)
        @given(series=_synthetic_series())
        def test_engine_handles_various_volatilities(self, series: np.ndarray) -> None:
            dates = pd.date_range("2024-01-01", periods=len(series), freq="1min")
            df = pd.DataFrame(
                {"close": series, "volume": np.full(len(series), 1000.0)}, index=dates
            )

            engine = TradePulseCompositeEngine()
            signal = engine.analyze_market(df)
            assert signal.phase in MarketPhase
            assert not np.isnan(signal.confidence)

else:  # pragma: no cover - Hypothesis not available

    class TestPropertyBased:  # type: ignore[no-redef]
        def test_engine_handles_various_volatilities(self) -> None:
            pytest.skip("hypothesis not installed")
