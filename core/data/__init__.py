# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Core data utilities and models for TradePulse."""

from __future__ import annotations

import os

_LIGHT_IMPORT = os.environ.get("TRADEPULSE_LIGHT_DATA_IMPORT") == "1"

if not _LIGHT_IMPORT:
    import numpy as _np

    if not hasattr(_np, "string_"):
        _np.string_ = _np.bytes_
    if not hasattr(_np, "float_"):
        _np.float_ = _np.float64

    from .asset_catalog import AssetCatalog, AssetRecord, AssetStatus
    from .catalog import normalize_symbol, normalize_venue
    from .feature_catalog import CatalogEntry, FeatureCatalog
    from .feature_store import (
        FeatureStoreIntegrityError,
        IntegrityReport,
        OnlineFeatureStore,
    )
    from .materialization import (
        Checkpoint,
        CheckpointStore,
        InMemoryCheckpointStore,
        StreamMaterializer,
    )
    from .models import (
        AggregateMetric,
        DataKind,
        InstrumentType,
        MarketDataPoint,
        MarketMetadata,
        OHLCVBar,
        PriceTick,
        Ticker,
    )
    from .normalization_pipeline import (
        FillMethod,
        MarketNormalizationConfig,
        MarketNormalizationMetadata,
        MarketNormalizationResult,
        NormalisationKind,
        normalize_market_data,
    )
    from .parity import (
        FeatureParityCoordinator,
        FeatureParityError,
        FeatureParityReport,
        FeatureParitySpec,
        FeatureTimeSkewError,
        FeatureUpdateBlocked,
    )
    from .pipeline import (
        AnonymizationRule,
        BalanceConfig,
        DataPipeline,
        DataPipelineConfig,
        DataPipelineResult,
        PipelineConfigurationError,
        PipelineContext,
        PipelineError,
        PipelineExecutionError,
        PipelineSLAError,
        SLAConfig,
        SourceOfTruthSpec,
        StratifiedSplitConfig,
        SyntheticAugmentationConfig,
        ToxicityFilterConfig,
        build_online_writer,
    )
    from .signal_filter import (
        FilterResult,
        FilterStrategy,
        SignalFilterConfig,
        SignalFilterConfigError,
        filter_by_quality,
        filter_by_range,
        filter_dataframe,
        filter_duplicates,
        filter_invalid_values,
        filter_outliers_zscore,
        filter_signals,
    )
    from .validation import (
        TimeSeriesValidationConfig,
        TimeSeriesValidationError,
        ValueColumnConfig,
        build_timeseries_schema,
        validate_timeseries_frame,
    )
    from .versioning import DataVersionManager, VersioningError

    try:
        from .timeutils import (
            MarketCalendar,
            MarketCalendarRegistry,
            convert_timestamp,
            get_market_calendar,
            get_timezone,
            is_market_open,
            normalize_timestamp,
            to_utc,
            validate_bar_alignment,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency guard
        if exc.name != "exchange_calendars":
            raise

        def _missing_dependency(*_args, **_kwargs):
            raise ModuleNotFoundError(
                "exchange_calendars is required for timeutils functionality in core.data"
            )

        MarketCalendar = MarketCalendarRegistry = object  # type: ignore
        convert_timestamp = get_market_calendar = get_timezone = is_market_open = (
            _missing_dependency
        )
        normalize_timestamp = to_utc = validate_bar_alignment = _missing_dependency

    __all__ = [
        "AggregateMetric",
        "AssetCatalog",
        "AssetRecord",
        "AssetStatus",
        "DataKind",
        "InstrumentType",
        "MarketCalendar",
        "MarketCalendarRegistry",
        "MarketDataPoint",
        "MarketMetadata",
        "OHLCVBar",
        "PriceTick",
        "Ticker",
        "normalize_symbol",
        "normalize_venue",
        "CatalogEntry",
        "FeatureCatalog",
        "FeatureParityCoordinator",
        "FeatureParityError",
        "FeatureParityReport",
        "FeatureParitySpec",
        "FeatureStoreIntegrityError",
        "IntegrityReport",
        "OnlineFeatureStore",
        "FeatureTimeSkewError",
        "FeatureUpdateBlocked",
        "Checkpoint",
        "CheckpointStore",
        "InMemoryCheckpointStore",
        "StreamMaterializer",
        "FillMethod",
        "MarketNormalizationConfig",
        "MarketNormalizationMetadata",
        "MarketNormalizationResult",
        "NormalisationKind",
        "normalize_market_data",
        "DataVersionManager",
        "VersioningError",
        "TimeSeriesValidationConfig",
        "TimeSeriesValidationError",
        "ValueColumnConfig",
        "build_timeseries_schema",
        "validate_timeseries_frame",
        "convert_timestamp",
        "get_market_calendar",
        "is_market_open",
        "normalize_timestamp",
        "to_utc",
        "get_timezone",
        "validate_bar_alignment",
        "AnonymizationRule",
        "BalanceConfig",
        "DataPipeline",
        "DataPipelineConfig",
        "DataPipelineResult",
        "PipelineConfigurationError",
        "PipelineContext",
        "PipelineError",
        "PipelineExecutionError",
        "PipelineSLAError",
        "SLAConfig",
        "SourceOfTruthSpec",
        "StratifiedSplitConfig",
        "SyntheticAugmentationConfig",
        "ToxicityFilterConfig",
        "build_online_writer",
        "FilterResult",
        "FilterStrategy",
        "SignalFilterConfig",
        "SignalFilterConfigError",
        "filter_by_quality",
        "filter_by_range",
        "filter_dataframe",
        "filter_duplicates",
        "filter_invalid_values",
        "filter_outliers_zscore",
        "filter_signals",
    ]
else:  # pragma: no cover - lightweight import path for governance scripts
    __all__: list[str] = []
