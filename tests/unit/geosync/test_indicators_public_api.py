# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync.indicators module public API."""

import numpy as np
import pandas as pd


class TestIndicatorsModuleImports:
    """Test that all public API imports work correctly."""

    def test_import_multiscale_kuramoto(self) -> None:
        """Test MultiscaleKuramoto import from geosync.indicators."""
        from geosync.indicators import MultiscaleKuramoto

        assert MultiscaleKuramoto is not None

    def test_import_multi_scale_kuramoto(self) -> None:
        """Test MultiScaleKuramoto import from geosync.indicators."""
        from geosync.indicators import MultiScaleKuramoto

        assert MultiScaleKuramoto is not None

    def test_multiscale_kuramoto_is_alias(self) -> None:
        """Test that MultiscaleKuramoto is an alias for MultiScaleKuramoto."""
        from geosync.indicators import MultiScaleKuramoto, MultiscaleKuramoto

        assert MultiscaleKuramoto is MultiScaleKuramoto

    def test_import_kuramoto_indicator(self) -> None:
        """Test KuramotoIndicator import from geosync.indicators."""
        from geosync.indicators import KuramotoIndicator

        assert KuramotoIndicator is not None

    def test_import_geosync_composite_engine(self) -> None:
        """Test GeoSyncCompositeEngine import."""
        from geosync.indicators import GeoSyncCompositeEngine

        assert GeoSyncCompositeEngine is not None

    def test_import_market_phase(self) -> None:
        """Test MarketPhase enum import."""
        from geosync.indicators import MarketPhase

        assert MarketPhase is not None

    def test_import_timeframe(self) -> None:
        """Test TimeFrame enum import."""
        from geosync.indicators import TimeFrame

        assert TimeFrame is not None


class TestIndicatorsBasicUsage:
    """Test basic usage of indicator classes."""

    def test_multiscale_kuramoto_analyze(self) -> None:
        """Test MultiScaleKuramoto analysis with minimal data."""
        from geosync.indicators import MultiScaleKuramoto

        # Create minimal test data
        np.random.seed(42)
        idx = pd.date_range("2024-01-01", periods=500, freq="1min")
        prices = 100 + np.cumsum(np.random.normal(0, 0.5, 500))
        df = pd.DataFrame({"close": prices}, index=idx)

        analyzer = MultiScaleKuramoto(
            base_window=64,
            min_samples_per_scale=32,
        )
        result = analyzer.analyze(df)

        assert result is not None
        assert 0.0 <= result.consensus_R <= 1.0
        assert result.adaptive_window > 0

    def test_kuramoto_indicator_compute(self) -> None:
        """Test KuramotoIndicator compute method."""
        from geosync.indicators import KuramotoIndicator

        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.normal(0, 0.5, 200))

        indicator = KuramotoIndicator(window=50)
        result = indicator.compute(prices)

        assert result is not None
        assert len(result) == len(prices)

    def test_geosync_composite_engine(self) -> None:
        """Test GeoSyncCompositeEngine analysis."""
        from geosync.indicators import GeoSyncCompositeEngine

        np.random.seed(42)
        idx = pd.date_range("2024-01-01", periods=500, freq="5min")
        prices = 100 + np.cumsum(np.random.normal(0, 0.5, 500))
        volume = np.random.lognormal(10, 1, 500)
        df = pd.DataFrame({"close": prices, "volume": volume}, index=idx)

        engine = GeoSyncCompositeEngine()
        snapshot = engine.analyze_market(df)

        assert snapshot is not None
        assert snapshot.phase is not None
        assert 0.0 <= snapshot.confidence <= 1.0


class TestIndicatorsAllExports:
    """Test that all expected exports are available."""

    def test_all_kuramoto_exports(self) -> None:
        """Test Kuramoto-related exports."""
        from geosync.indicators import (
            KuramotoIndicator,
            KuramotoOrderFeature,
            KuramotoResult,
            KuramotoRicciComposite,
            MultiAssetKuramotoFeature,
            MultiScaleKuramoto,
            MultiScaleKuramotoFeature,
            MultiScaleResult,
            compute_phase,
            kuramoto_order,
            multi_asset_kuramoto,
        )

        assert all(
            x is not None
            for x in [
                KuramotoIndicator,
                KuramotoOrderFeature,
                KuramotoResult,
                KuramotoRicciComposite,
                MultiAssetKuramotoFeature,
                MultiScaleKuramoto,
                MultiScaleKuramotoFeature,
                MultiScaleResult,
                compute_phase,
                kuramoto_order,
                multi_asset_kuramoto,
            ]
        )

    def test_all_pipeline_exports(self) -> None:
        """Test pipeline-related exports."""
        from geosync.indicators import (
            BackfillState,
            CacheRecord,
            FileSystemIndicatorCache,
            IndicatorPipeline,
            PipelineResult,
            cache_indicator,
            hash_input_data,
            make_fingerprint,
        )

        assert all(
            x is not None
            for x in [
                BackfillState,
                CacheRecord,
                FileSystemIndicatorCache,
                IndicatorPipeline,
                PipelineResult,
                cache_indicator,
                hash_input_data,
                make_fingerprint,
            ]
        )

    def test_all_normalization_exports(self) -> None:
        """Test normalization-related exports."""
        from geosync.indicators import (
            IndicatorNormalizationConfig,
            IndicatorNormalizer,
            NormalizationMode,
            normalize_indicator_series,
            resolve_indicator_normalizer,
        )

        assert all(
            x is not None
            for x in [
                IndicatorNormalizationConfig,
                IndicatorNormalizer,
                NormalizationMode,
                normalize_indicator_series,
                resolve_indicator_normalizer,
            ]
        )
