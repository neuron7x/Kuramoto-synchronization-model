from datetime import UTC

import pandas as pd
import pytest

from core.data.feature_store import OnlineFeatureStore
from core.data.parity import (
    FeatureParityCoordinator,
    FeatureParityReport,
    FeatureParitySpec,
    FeatureTimeSkewError,
    FeatureUpdateBlocked,
)


@pytest.fixture
def parity_spec() -> FeatureParitySpec:
    return FeatureParitySpec(
        feature_view="prices",
        timestamp_granularity="1min",
        numeric_tolerance=0.0,
        max_clock_skew=pd.Timedelta(minutes=5),
    )


def _make_frame(ts_values: list[str], values: list[float]) -> pd.DataFrame:
    timestamps = [pd.Timestamp(item, tz=UTC) for item in ts_values]
    return pd.DataFrame(
        {"entity_id": ["A"] * len(values), "ts": timestamps, "value": values}
    )


def test_parity_coordinator_validates_empty_frames(tmp_path) -> None:
    store = OnlineFeatureStore(tmp_path)
    coordinator = FeatureParityCoordinator(store)
    spec = FeatureParitySpec(feature_view="prices", allow_schema_evolution=True)

    empty = pd.DataFrame()

    with pytest.raises(KeyError, match="missing required columns"):
        coordinator.synchronize(spec, empty, mode="overwrite")


def test_parity_coordinator_overwrite_success(tmp_path, parity_spec) -> None:
    store = OnlineFeatureStore(tmp_path)
    coordinator = FeatureParityCoordinator(store)

    offline = _make_frame(
        ["2024-01-01T00:00:30Z", "2024-01-01T00:01:15Z"],
        [1.0, 2.0],
    )

    report = coordinator.synchronize(parity_spec, offline, mode="overwrite")

    assert isinstance(report, FeatureParityReport)
    assert report.inserted_rows == 2
    assert report.updated_rows == 0
    assert report.dropped_rows == 0
    assert report.integrity.hash_differs is False

    stored = store.load("prices")
    assert list(stored.columns) == ["entity_id", "ts", "value"]
    assert stored.shape[0] == 2
    assert set(stored["ts"]) == {
        pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC),
        pd.Timestamp("2024-01-01T00:01:00Z", tz=UTC),
    }


def test_parity_coordinator_blocks_excessive_clock_skew(tmp_path, parity_spec) -> None:
    store = OnlineFeatureStore(tmp_path)
    coordinator = FeatureParityCoordinator(store)

    initial = _make_frame(["2024-01-01T00:00:00Z"], [1.0])
    coordinator.synchronize(parity_spec, initial, mode="overwrite")

    skewed = _make_frame(["2024-01-01T00:10:00Z"], [1.5])
    spec = FeatureParitySpec(
        feature_view="prices",
        timestamp_granularity="1min",
        numeric_tolerance=0.0,
        max_clock_skew=pd.Timedelta(minutes=2),
    )

    with pytest.raises(FeatureTimeSkewError):
        coordinator.synchronize(spec, skewed, mode="append")


def test_parity_coordinator_blocks_feature_drift(tmp_path, parity_spec) -> None:
    store = OnlineFeatureStore(tmp_path)
    coordinator = FeatureParityCoordinator(store)

    baseline = _make_frame(["2024-01-01T00:00:00Z"], [1.0])
    coordinator.synchronize(parity_spec, baseline, mode="overwrite")

    drifted = _make_frame(["2024-01-01T00:00:30Z"], [2.0])

    with pytest.raises(FeatureUpdateBlocked, match="drift exceeds"):
        coordinator.synchronize(parity_spec, drifted, mode="overwrite")


def test_parity_coordinator_allows_schema_evolution_on_overwrite(tmp_path) -> None:
    store = OnlineFeatureStore(tmp_path)
    coordinator = FeatureParityCoordinator(store)

    baseline = _make_frame(["2024-01-01T00:00:00Z"], [1.0])
    spec = FeatureParitySpec(
        feature_view="prices",
        timestamp_granularity="1min",
        numeric_tolerance=0.0,
        max_clock_skew=pd.Timedelta(minutes=5),
    )
    coordinator.synchronize(spec, baseline, mode="overwrite")

    evolved = _make_frame(["2024-01-01T00:05:00Z"], [1.5])
    evolved["confidence"] = [0.9]

    evolving_spec = FeatureParitySpec(
        feature_view="prices",
        timestamp_granularity="1min",
        numeric_tolerance=0.0,
        max_clock_skew=pd.Timedelta(minutes=5),
        allow_schema_evolution=True,
    )

    report = coordinator.synchronize(evolving_spec, evolved, mode="overwrite")
    assert report.columns_added == ("confidence",)
    assert store.load("prices").columns.tolist() == [
        "entity_id",
        "ts",
        "value",
        "confidence",
    ]


def test_parity_coordinator_append_skips_duplicate_rows(tmp_path, parity_spec) -> None:
    store = OnlineFeatureStore(tmp_path)
    coordinator = FeatureParityCoordinator(store)

    initial = _make_frame(["2024-01-01T00:00:00Z"], [1.0])
    coordinator.synchronize(parity_spec, initial, mode="overwrite")

    duplicate = _make_frame(["2024-01-01T00:00:15Z"], [1.0])
    report = coordinator.synchronize(parity_spec, duplicate, mode="append")

    assert report.inserted_rows == 0
    assert store.load("prices").shape[0] == 1
