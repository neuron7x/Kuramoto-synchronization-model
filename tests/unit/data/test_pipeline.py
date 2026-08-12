# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections import Counter
from datetime import UTC
from pathlib import Path

import pandas as pd
import pytest

from core.data.backfill import (
    BackfillPlan,
    BackfillProgressSnapshot,
    BackfillResult,
    CacheKey,
)
from core.data.dead_letter import DeadLetterQueue, DeadLetterReason
from core.data.feature_store import OnlineFeatureStore
from core.data.pipeline import (
    AnonymizationRule,
    BalanceConfig,
    DataPipeline,
    DataPipelineConfig,
    PipelineContext,
    PipelineSLAError,
    SLAConfig,
    SourceOfTruthSpec,
    StratifiedSplitConfig,
    SyntheticAugmentationConfig,
    ToxicityFilterConfig,
    build_online_writer,
)
from core.data.quality_control import QualityGateConfig, RangeCheck
from core.data.validation import TimeSeriesValidationConfig, ValueColumnConfig
from observability.drift import DriftDetector


def _primary_source_factory(frame: pd.DataFrame) -> SourceOfTruthSpec:
    def _loader(_: PipelineContext) -> pd.DataFrame:
        return frame

    return SourceOfTruthSpec(
        name="primary",
        loader=_loader,
        datasets=frozenset({"ohlcv"}),
        priority=0,
    )


def _fallback_source() -> SourceOfTruthSpec:
    def _loader(_: PipelineContext) -> pd.DataFrame:
        return pd.DataFrame()

    return SourceOfTruthSpec(name="fallback", loader=_loader, priority=100)


def _build_frame() -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=8, freq="1min", tz=UTC)
    payload = pd.DataFrame(
        {
            "timestamp": timestamps,
            "price": [
                100.0,
                101.0,
                300.0,  # spike quarantined by quality gate
                102.0,
                103.0,
                104.0,
                105.0,
                106.0,
            ],
            "volume": [10, 11, 0, 9, 10, 8, 12, 9],
            "toxicity_score": [0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0],
            "pii": [
                "user-1",
                "user-2",
                "user-3",
                "user-4",
                "user-5",
                "user-6",
                "user-7",
                "user-8",
            ],
            "label": ["A", "A", "B", "B", "B", "A", "B", "A"],
        }
    )
    duplicate = payload.iloc[[0]].copy()
    duplicate["price"] = 100.5
    duplicate["timestamp"] = payload.iloc[0]["timestamp"]
    return pd.concat([payload, duplicate], ignore_index=True)


def _reference_frame(frame: pd.DataFrame) -> pd.DataFrame:
    baseline = frame.copy()
    baseline.loc[:, "price"] = baseline["price"].clip(upper=110.0)
    return baseline


@pytest.mark.parametrize("strict_sla", [False, True])
def test_pipeline_end_to_end(tmp_path: Path, strict_sla: bool) -> None:
    frame = _build_frame()
    source = _primary_source_factory(frame)
    fallback = _fallback_source()

    schema = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=(
            ValueColumnConfig(name="price", dtype="float64"),
            ValueColumnConfig(name="volume", dtype="float64"),
        ),
        require_timezone="UTC",
        allow_extra_columns=True,
    )
    gate = QualityGateConfig(
        schema=schema,
        price_column="price",
        anomaly_threshold=2.0,
        anomaly_window=3,
        range_checks=(RangeCheck(column="volume", min_value=0, max_value=20),),
        max_quarantine_fraction=0.5,
    )

    queue = DeadLetterQueue(max_items=128, toxicity_threshold=2)

    class StubBackfillPlanner:
        def __init__(self) -> None:
            self.invocations = 0

        def backfill(
            self,
            key: CacheKey,
            *,
            expected_index: pd.Index,
            loader,
            frequency=None,
            progress_callback=None,
        ) -> BackfillResult:
            self.invocations += 1
            plan = BackfillPlan()
            snapshot = BackfillProgressSnapshot(
                total_segments=0,
                completed_segments=0,
                failed_segments=0,
                bytes_transferred=0,
            )
            return BackfillResult(
                plan=plan,
                completed_segments=[],
                failed_segments=[],
                errors=[],
                progress=snapshot,
            )

    planner = StubBackfillPlanner()

    offline_sink: dict[str, dict[str, object]] = {}

    def offline_writer(
        dataset: str, payload: pd.DataFrame, *, metadata: dict[str, object]
    ) -> None:
        offline_sink[dataset] = {"frame": payload.copy(), "metadata": dict(metadata)}

    online_store = OnlineFeatureStore(tmp_path / "online")
    online_writer = build_online_writer(online_store)

    config = DataPipelineConfig(
        sources=(source, fallback),
        schema_registry={"ohlcv": schema},
        quality_gates={"ohlcv": gate},
        toxicity_filter=ToxicityFilterConfig(column="toxicity_score", threshold=3.0),
        anonymization_rules=(
            AnonymizationRule(column="pii", salt=b"unit-test", keep_last_chars=2),
        ),
        balance=BalanceConfig(column="label"),
        stratified_split=StratifiedSplitConfig(
            column="label", splits={"train": 0.5, "validation": 0.25}
        ),
        synthetic=SyntheticAugmentationConfig(samples=2, noise_scale=0.05),
        drift_detector=DriftDetector(psi_threshold=0.2, ks_confidence=0.9, bins=4),
        dead_letter=queue,
        backfill_planner=planner,
        sla=SLAConfig(
            target_seconds=(5.0 if not strict_sla else 1e-9), strict=strict_sla
        ),
        offline_writer=offline_writer,
        online_writer=online_writer,
        random_seed=42,
    )
    pipeline = DataPipeline(config)

    expected_index = pd.Index(
        frame.loc[
            (frame["toxicity_score"] <= 3.0) & (frame["price"] < 200.0), "timestamp"
        ]
        .drop_duplicates()
        .sort_values()
    )
    context = PipelineContext(
        dataset="ohlcv",
        metadata={"symbol": "BTCUSDT"},
        reference_frame=_reference_frame(frame),
        expected_index=expected_index,
        backfill=True,
        cache_key=CacheKey(
            layer="ohlcv", symbol="BTCUSDT", venue="BINANCE", timeframe="1m"
        ),
        feature_view="feature/btcusdt",
        offline_dataset="dataset/btcusdt",
    )

    if strict_sla:
        with pytest.raises(PipelineSLAError):
            pipeline.run(context)
        return

    result = pipeline.run(context)

    assert result.dataset == "ohlcv"
    assert result.source == "primary"
    assert result.clean_frame.shape[0] >= expected_index.shape[0]
    assert result.toxic_frame.shape[0] == 1
    assert result.quarantined_frame.shape[0] >= 1
    reasons = {item.reason for item in queue.peek()}
    assert DeadLetterReason.VALIDATION_ERROR in reasons
    assert DeadLetterReason.TOXIC_PAYLOAD in reasons

    # Anonymisation preserves suffix and hashes prefix
    anonymised_values = result.clean_frame["pii"].unique()
    suffixes = {value.split(":")[-1] for value in anonymised_values}
    assert suffixes <= {"-1", "-2", "-3", "-4", "-5", "-6", "-7", "-8"}
    assert all("user" not in value for value in anonymised_values)

    counts = Counter(result.clean_frame["label"])
    assert len(set(counts.values())) == 1  # perfectly balanced across classes

    splits = result.stratified_splits
    assert set(splits) == {"train", "validation", "remainder"}
    assert (
        sum(split.shape[0] for split in splits.values()) == result.clean_frame.shape[0]
    )

    assert result.synthetic_frame.shape[0] == 2
    assert "synthetic" in result.synthetic_frame.columns

    assert result.drift_summaries
    assert all(
        summary.feature.startswith("ohlcv:") for summary in result.drift_summaries
    )

    assert result.backfill_result is not None
    assert planner.invocations == 1

    persisted = offline_sink["dataset/btcusdt"]
    assert isinstance(persisted["metadata"], dict)
    assert persisted["frame"].shape[0] == result.clean_frame.shape[0]

    online_payload = online_store.load("feature/btcusdt")
    assert online_payload.shape[0] == result.clean_frame.shape[0]

    assert result.sla_met is True
    assert result.metadata["symbol"] == "BTCUSDT"
