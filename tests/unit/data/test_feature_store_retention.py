from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from core.data.feature_store import (
    DeltaLakeSource,
    FeatureStoreIntegrityError,
    IntegrityReport,
    OfflineStoreValidator,
    OnlineFeatureStore,
    RedisOnlineFeatureStore,
    RetentionPolicy,
    SQLiteEncryptionConfig,
    SQLiteOnlineFeatureStore,
)
from core.utils.dataframe_io import write_dataframe


class _MutableClock:
    def __init__(self, now: pd.Timestamp) -> None:
        self._now = now

    def now(self) -> pd.Timestamp:
        return self._now

    def advance(self, delta: pd.Timedelta) -> None:
        self._now = self._now + delta


class _DictClient:
    def __init__(self) -> None:
        self.payloads: dict[str, bytes] = {}

    def get(self, key: str):  # pragma: no cover - trivial
        return self.payloads.get(key)

    def set(self, key: str, value: bytes) -> None:
        self.payloads[key] = value

    def delete(self, key: str) -> None:  # pragma: no cover - defensive
        self.payloads.pop(key, None)


class _TTLDictClient(_DictClient):
    def __init__(self) -> None:
        super().__init__()
        self.expiries: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: bytes) -> None:
        self.payloads[key] = value
        self.expiries[key] = ttl


@pytest.fixture
def base_frame() -> pd.DataFrame:
    ts = pd.Timestamp("2024-01-01 00:00:00", tz=UTC)
    return pd.DataFrame(
        {
            "entity_id": ["a", "a", "b"],
            "ts": [
                ts - pd.Timedelta(hours=2),
                ts - pd.Timedelta(minutes=30),
                ts - pd.Timedelta(minutes=5),
            ],
            "value": [1.0, 2.0, 3.0],
        }
    )


@pytest.fixture
def sqlite_encryption_config() -> SQLiteEncryptionConfig:
    return SQLiteEncryptionConfig(key_id="v1", key_material="primary-secret")


def test_redis_ttl_retention(base_frame: pd.DataFrame) -> None:
    clock = _MutableClock(pd.Timestamp("2024-01-01 00:00:00", tz=UTC))
    policy = RetentionPolicy(ttl=pd.Timedelta(hours=1))
    store = RedisOnlineFeatureStore(
        client=_DictClient(), retention_policy=policy, clock=clock.now
    )

    store.sync("demo.fv", base_frame, mode="overwrite", validate=False)
    stored = store.load("demo.fv")
    assert stored.shape[0] == 2
    assert stored["ts"].min() >= clock.now() - pd.Timedelta(hours=1)


def test_retention_casts_string_timestamps(base_frame: pd.DataFrame) -> None:
    clock = _MutableClock(pd.Timestamp("2024-01-01 00:00:00", tz=UTC))
    policy = RetentionPolicy(ttl=pd.Timedelta(hours=1))
    store = RedisOnlineFeatureStore(
        client=_DictClient(), retention_policy=policy, clock=clock.now
    )

    string_frame = base_frame.copy()
    string_frame.loc[:, "ts"] = string_frame["ts"].dt.tz_convert("UTC").dt.strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )

    store.sync("demo.fv", string_frame, mode="overwrite", validate=False)

    stored = store.load("demo.fv")
    assert stored.shape[0] == 2
    assert stored["ts"].dtype == "datetime64[ns, UTC]"
    assert stored["ts"].min() >= clock.now() - pd.Timedelta(hours=1)


def test_redis_ttl_uses_native_expiry(base_frame: pd.DataFrame) -> None:
    client = _TTLDictClient()
    policy = RetentionPolicy(ttl=pd.Timedelta(seconds=90))
    store = RedisOnlineFeatureStore(client=client, retention_policy=policy)

    store.sync("demo.fv", base_frame, mode="overwrite", validate=False)

    assert client.expiries["demo.fv"] == 90


def test_sqlite_max_versions(
    tmp_path,
    base_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    policy = RetentionPolicy(max_versions=1)
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db",
        encryption=sqlite_encryption_config,
        retention_policy=policy,
    )

    store.sync("demo.fv", base_frame, mode="overwrite", validate=False)
    newer = base_frame.copy()
    newer.loc[:, "value"] = [10.0, 11.0, 12.0]
    newer.loc[:, "ts"] = newer["ts"] + pd.Timedelta(minutes=10)
    store.sync("demo.fv", newer, mode="append", validate=False)

    stored = store.load("demo.fv")
    assert stored.shape[0] == 2
    assert stored["ts"].is_monotonic_increasing


def test_offline_validator_detects_mismatch(tmp_path, base_frame: pd.DataFrame) -> None:
    offline_path = tmp_path / "delta"
    write_dataframe(base_frame, offline_path, allow_json_fallback=True)
    source = DeltaLakeSource(offline_path)

    # Drop the latest row to trigger an integrity failure.
    online_payload = base_frame.iloc[:-1]

    def loader(_name: str) -> pd.DataFrame:
        return online_payload

    validator = OfflineStoreValidator(
        "demo.fv",
        source,
        loader,
        interval=pd.Timedelta(minutes=5),
        clock=lambda: pd.Timestamp("2024-01-01 00:00:00", tz=UTC),
    )

    with pytest.raises(FeatureStoreIntegrityError):
        validator.run()


def test_offline_validator_respects_interval(
    tmp_path, base_frame: pd.DataFrame
) -> None:
    offline_path = tmp_path / "delta"
    write_dataframe(base_frame, offline_path, allow_json_fallback=True)
    source = DeltaLakeSource(offline_path)

    clock = _MutableClock(pd.Timestamp("2024-01-01 00:00:00", tz=UTC))
    validator = OfflineStoreValidator(
        "demo.fv",
        source,
        lambda _name: base_frame,
        interval=pd.Timedelta(hours=1),
        clock=clock.now,
    )

    assert validator.should_run() is True
    validator.run()
    assert validator.should_run() is False
    clock.advance(pd.Timedelta(minutes=59))
    assert validator.should_run() is False
    clock.advance(pd.Timedelta(minutes=1))
    assert validator.should_run() is True


def test_offline_validator_numeric_type_equivalence(
    tmp_path, base_frame: pd.DataFrame
) -> None:
    offline_path = tmp_path / "delta"
    offline_payload = base_frame.copy()
    offline_payload.loc[:, "value"] = offline_payload["value"].astype("Int64")
    write_dataframe(offline_payload, offline_path, allow_json_fallback=True)
    source = DeltaLakeSource(offline_path)

    validator = OfflineStoreValidator(
        "demo.fv",
        source,
        lambda _name: base_frame,
        interval=pd.Timedelta(minutes=5),
        clock=lambda: pd.Timestamp("2024-01-01 00:00:00", tz=UTC),
    )

    report = validator.run()
    assert report.hash_differs is False


def test_retention_policy_validation() -> None:
    with pytest.raises(ValueError):
        RetentionPolicy(ttl=pd.Timedelta(0))
    with pytest.raises(ValueError):
        RetentionPolicy(max_versions=0)


def test_ttl_requires_timestamp_column() -> None:
    store = RedisOnlineFeatureStore(
        client=_DictClient(),
        retention_policy=RetentionPolicy(ttl=pd.Timedelta(minutes=5)),
    )
    payload = pd.DataFrame({"entity_id": ["a"], "value": [1.0]})

    with pytest.raises(KeyError, match="'ts'"):
        store.sync("demo.fv", payload, mode="overwrite", validate=False)


def test_max_versions_requires_entity_identifier() -> None:
    ts = pd.Timestamp("2024-01-01 00:00:00", tz=UTC)
    store = RedisOnlineFeatureStore(
        client=_DictClient(), retention_policy=RetentionPolicy(max_versions=1)
    )
    payload = pd.DataFrame({"ts": [ts], "value": [1.0]})

    with pytest.raises(KeyError, match="entity_id"):
        store.sync("demo.fv", payload, mode="overwrite", validate=False)


def test_redis_sync_validates_mode(base_frame: pd.DataFrame) -> None:
    store = RedisOnlineFeatureStore(client=_DictClient())

    with pytest.raises(ValueError):
        store.sync("demo.fv", base_frame, mode="invalid", validate=False)


def test_redis_append_enforces_schema(base_frame: pd.DataFrame) -> None:
    store = RedisOnlineFeatureStore(client=_DictClient())
    store.sync("demo.fv", base_frame, mode="overwrite")

    with pytest.raises(ValueError):
        store.sync("demo.fv", base_frame.drop(columns=["value"]), mode="append")


def test_redis_append_returns_delta(base_frame: pd.DataFrame) -> None:
    store = RedisOnlineFeatureStore(client=_DictClient())
    report = store.sync("demo.fv", base_frame, mode="overwrite")
    assert report.row_count_diff == 0

    newer = base_frame.copy()
    newer.loc[:, "value"] = [10.0, 11.0, 12.0]
    newer.loc[:, "ts"] = newer["ts"] + pd.Timedelta(minutes=5)

    report = store.sync("demo.fv", newer, mode="append")
    assert report.offline_rows == newer.shape[0]
    assert report.online_rows == newer.shape[0]
    stored = store.load("demo.fv")
    assert stored.shape[0] == base_frame.shape[0] + newer.shape[0]


def test_empty_payload_round_trip() -> None:
    client = _DictClient()
    store = RedisOnlineFeatureStore(client=client)
    client.payloads["demo.fv"] = b""

    loaded = store.load("demo.fv")
    assert loaded.empty


def test_sqlite_append_validates_schema(
    tmp_path,
    base_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db", encryption=sqlite_encryption_config
    )
    store.sync("demo.fv", base_frame, mode="overwrite")

    with pytest.raises(ValueError):
        store.sync("demo.fv", base_frame.drop(columns=["value"]), mode="append")


def test_sqlite_append_combines_rows(
    tmp_path,
    base_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db", encryption=sqlite_encryption_config
    )
    initial = store.sync("demo.fv", base_frame, mode="overwrite")
    assert initial.offline_rows == base_frame.shape[0]

    newer = base_frame.copy()
    newer.loc[:, "ts"] = newer["ts"] + pd.Timedelta(minutes=5)
    report = store.sync("demo.fv", newer, mode="append")

    assert report.row_count_diff == 0
    stored = store.load("demo.fv")
    assert stored.shape[0] == base_frame.shape[0] + newer.shape[0]


def test_online_feature_store_workflow(tmp_path, base_frame: pd.DataFrame) -> None:
    store = OnlineFeatureStore(tmp_path / "online")
    overwrite = store.sync("demo.fv", base_frame, mode="overwrite")
    assert overwrite.offline_rows == base_frame.shape[0]

    newer = base_frame.copy()
    newer.loc[:, "value"] = [5.0, 6.0, 7.0]
    newer.loc[:, "ts"] = newer["ts"] + pd.Timedelta(minutes=10)
    append_report = store.sync("demo.fv", newer, mode="append")
    assert append_report.row_count_diff == 0

    stored = store.load("demo.fv")
    assert stored.shape[0] == base_frame.shape[0] + newer.shape[0]

    integrity = store.compute_integrity("demo.fv", stored)
    assert integrity.row_count_diff == 0


def test_online_feature_store_invalid_mode(tmp_path, base_frame: pd.DataFrame) -> None:
    store = OnlineFeatureStore(tmp_path / "online")
    with pytest.raises(ValueError):
        store.sync("demo.fv", base_frame, mode="merge")


def test_integrity_report_validation_errors() -> None:
    base = IntegrityReport(
        feature_view="demo.fv",
        offline_rows=2,
        online_rows=3,
        row_count_diff=1,
        offline_hash="abc",
        online_hash="def",
        hash_differs=True,
    )

    with pytest.raises(FeatureStoreIntegrityError, match="Row count mismatch"):
        base.ensure_valid()

    consistent = IntegrityReport(
        feature_view="demo.fv",
        offline_rows=2,
        online_rows=2,
        row_count_diff=0,
        offline_hash="abc",
        online_hash="def",
        hash_differs=True,
    )

    with pytest.raises(FeatureStoreIntegrityError, match="Hash mismatch"):
        consistent.ensure_valid()


def test_canonicalize_sorts_and_stabilises_rows() -> None:
    frame = pd.DataFrame({"b": [2, 1], "a": [1, 2]})
    canonical = OnlineFeatureStore._canonicalize(frame)
    assert list(canonical.columns) == ["a", "b"]
    assert canonical.iloc[0].to_dict() == {"a": 1, "b": 2}
