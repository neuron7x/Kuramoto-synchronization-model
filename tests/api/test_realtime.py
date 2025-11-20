from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from application.api.realtime import AnalyticsStore


class _FeatureSnapshot(BaseModel):
    timestamp: datetime
    features: dict[str, float]


class _FeaturePayload(BaseModel):
    symbol: str
    generated_at: datetime
    features: dict[str, float]
    items: list[_FeatureSnapshot]


class _PredictionSnapshot(BaseModel):
    timestamp: datetime
    score: float
    signal: dict[str, float]


class _PredictionPayload(BaseModel):
    symbol: str
    generated_at: datetime
    horizon_seconds: int
    score: float
    signal: dict[str, float]
    items: list[_PredictionSnapshot]


@pytest.mark.asyncio()
async def test_analytics_store_records_and_snapshots() -> None:
    store = AnalyticsStore(history_limit=8)
    now = datetime.now(timezone.utc)

    feature_event = await store.record_feature(
        _FeaturePayload(
            symbol="BTC-USD",
            generated_at=now,
            features={"macd": 0.1},
            items=[
                _FeatureSnapshot(
                    timestamp=now,
                    features={"macd": 0.1},
                )
            ],
        )
    )

    prediction_event = await store.record_prediction(
        _PredictionPayload(
            symbol="BTC-USD",
            generated_at=now,
            horizon_seconds=900,
            score=0.75,
            signal={"action": 1.0},
            items=[
                _PredictionSnapshot(
                    timestamp=now,
                    score=0.75,
                    signal={"action": 1.0},
                )
            ],
        )
    )

    snapshot = await store.snapshot(limit=5)

    assert feature_event["type"] == "feature"
    assert prediction_event["type"] == "signal"
    assert snapshot["type"] == "snapshot"
    assert snapshot["features"][0]["symbol"] == "BTC-USD"
    assert snapshot["signals"][0]["symbol"] == "BTC-USD"

    latest_feature = await store.latest_feature("BTC-USD")
    latest_prediction = await store.latest_prediction("BTC-USD")

    assert latest_feature is not None and latest_feature.symbol == "BTC-USD"
    assert latest_prediction is not None and latest_prediction.symbol == "BTC-USD"


@pytest.mark.asyncio()
async def test_analytics_store_respects_history_limits() -> None:
    store = AnalyticsStore(history_limit=2)
    now = datetime.now(timezone.utc)

    for offset in range(4):
        await store.record_feature(
            _FeaturePayload(
                symbol=f"SYM-{offset}",
                generated_at=now,
                features={"value": float(offset)},
                items=[],
            )
        )

    records = await store.recent_features(limit=5)
    assert len(records) == 2
    assert records[0].symbol == "SYM-3"
    assert records[1].symbol == "SYM-2"
