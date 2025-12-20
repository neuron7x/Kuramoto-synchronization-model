# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import json
import math
import sqlite3
import ssl
from datetime import UTC
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pandas.io.json._table_schema import build_table_schema

from core.data.feature_store import (
    _ENVELOPE_PREFIX,
    DeltaLakeSource,
    FeatureStoreConfigurationError,
    FeatureStoreIntegrityError,
    IcebergSource,
    InMemoryKeyValueClient,
    IntegrityReport,
    KeyValueClient,
    OfflineStoreValidator,
    OnlineFeatureStore,
    RedisClientConfig,
    RedisOnlineFeatureStore,
    RetentionPolicy,
    SQLiteEncryptionConfig,
    SQLiteOnlineFeatureStore,
    _derive_aes_key,
    _format_numeric_value,
    _redis_client_uses_tls,
    _RetentionManager,
    _SQLiteEncryptionEnvelope,
    reencrypt_sqlite_payloads,
)
from core.utils.dataframe_io import write_dataframe


class _SetWithTTLClient:
    def __init__(self) -> None:
        self.payloads: dict[str, bytes] = {}
        self.calls: list[tuple[str, int, bytes]] = []

    def get(self, key: str):  # pragma: no cover - simple delegation
        return self.payloads.get(key)

    def set(
        self, key: str, value: bytes
    ) -> None:  # pragma: no cover - defensive fallback
        self.payloads[key] = value

    def delete(self, key: str) -> None:  # pragma: no cover - defensive fallback
        self.payloads.pop(key, None)

    def set_with_ttl(self, key: str, value: bytes, ttl: int) -> None:
        self.payloads[key] = value
        self.calls.append((key, ttl, value))


class _OnlySetClient:
    def __init__(self) -> None:
        self.payloads: dict[str, bytes] = {}
        self.calls: list[str] = []

    def get(self, key: str) -> bytes | None:  # pragma: no cover - defensive helper
        return self.payloads.get(key)

    def set(self, key: str, value: bytes) -> None:
        self.payloads[key] = value
        self.calls.append(key)

    def delete(self, key: str) -> None:  # pragma: no cover - defensive helper
        self.payloads.pop(key, None)


class _TrackingClient(_SetWithTTLClient):
    def __init__(self) -> None:
        super().__init__()
        self.set_calls: list[tuple[str, bytes]] = []

    def set(self, key: str, value: bytes) -> None:
        super().set(key, value)
        self.set_calls.append((key, value))


class _TestClock:
    def __init__(self, now: pd.Timestamp) -> None:
        self._now = now

    def now(self) -> pd.Timestamp:
        return self._now

    def advance(self, delta: pd.Timedelta) -> None:
        self._now = self._now + delta


class _FrameSource:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def load(self) -> pd.DataFrame:
        return self._frame


@pytest.fixture
def sample_frame() -> pd.DataFrame:
    ts = pd.Timestamp("2024-01-01T00:00:00Z", tz=UTC)
    return pd.DataFrame(
        {
            "entity_id": ["a", "b"],
            "ts": [ts, ts + pd.Timedelta(minutes=5)],
            "value": [1.0, 2.0],
        }
    )


def _table_orient_payload(frame: pd.DataFrame) -> bytes:
    schema = build_table_schema(frame, index=False)
    records: list[dict[str, Any]] = []

    for row in frame.to_dict(orient="records"):
        encoded: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, pd.Timestamp):
                encoded[key] = value.isoformat(timespec="nanoseconds").replace(
                    "+00:00", "Z"
                )
            else:
                encoded[key] = value
        records.append(encoded)

    return json.dumps(
        {"schema": schema, "data": records},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@pytest.fixture
def sqlite_encryption_config() -> SQLiteEncryptionConfig:
    return SQLiteEncryptionConfig(key_id="v1", key_material="primary-secret")


def test_derive_aes_key_rejects_empty_material() -> None:
    with pytest.raises(FeatureStoreConfigurationError):
        _derive_aes_key(b"")


def test_derive_aes_key_returns_exact_length_bytes() -> None:
    material = b"x" * 16
    assert _derive_aes_key(material) is material


def test_sqlite_encryption_config_validates_identifiers() -> None:
    with pytest.raises(ValueError, match="key_id"):
        SQLiteEncryptionConfig(key_id="", key_material="secret")

    too_long = "a" * 300
    with pytest.raises(ValueError, match="255 bytes"):
        SQLiteEncryptionConfig(key_id=too_long, key_material="secret")

    with pytest.raises(ValueError, match="fallback key identifiers cannot be empty"):
        SQLiteEncryptionConfig(
            key_id="v1", key_material="secret", fallback_keys={"": b"a"}
        )

    with pytest.raises(ValueError, match="fallback key identifiers must not exceed"):
        SQLiteEncryptionConfig(
            key_id="v1",
            key_material="secret",
            fallback_keys={"a" * 300: b"material"},
        )


def test_retention_manager_ttl_seconds_handles_absent_policy() -> None:
    manager = _RetentionManager(None)
    assert manager.ttl_seconds() is None


def test_retention_manager_ttl_seconds_rounds_up() -> None:
    policy = RetentionPolicy(ttl=pd.Timedelta(seconds=1.2))
    manager = _RetentionManager(policy)
    assert manager.ttl_seconds() == 2


def test_redis_persist_uses_set_with_ttl(sample_frame: pd.DataFrame) -> None:
    client = _SetWithTTLClient()
    policy = RetentionPolicy(ttl=pd.Timedelta(seconds=30))
    store = RedisOnlineFeatureStore(client=client, retention_policy=policy)
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    assert client.calls == [("demo.view", 30, client.payloads["demo.view"])]


def test_redis_persist_with_plain_client_uses_set(sample_frame: pd.DataFrame) -> None:
    client = _OnlySetClient()
    policy = RetentionPolicy(ttl=pd.Timedelta(seconds=45))
    store = RedisOnlineFeatureStore(client=client, retention_policy=policy)

    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)

    assert client.calls == ["demo.view"]


def test_redis_rejects_non_tls_client() -> None:
    class _PlainRedisClient:
        def __init__(self) -> None:
            self.connection_pool = type(
                "Pool", (), {"connection_kwargs": {"ssl": False, "ssl_context": None}}
            )()

    with pytest.raises(FeatureStoreConfigurationError):
        RedisOnlineFeatureStore(client=_PlainRedisClient())


def test_redis_tls_client_config(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Client:
        connection_pool = None

    def fake_from_url(url: str, **kwargs: Any) -> Any:
        captured["url"] = url
        captured.update(kwargs)
        return _Client()

    redis_module = pytest.importorskip("redis")
    monkeypatch.setattr(redis_module.Redis, "from_url", fake_from_url)
    monkeypatch.setattr("core.data.feature_store.redis", redis_module, raising=False)

    context = ssl.create_default_context()
    config = RedisClientConfig(
        url="rediss://example.com:6380/0",
        username="app-user",
        password="s3cret",
        ssl_context=context,
    )
    store = RedisOnlineFeatureStore(client_config=config)
    assert isinstance(store, RedisOnlineFeatureStore)
    assert captured["url"] == "rediss://example.com:6380/0"
    assert captured["username"] == "app-user"
    assert captured["password"] == "s3cret"
    assert captured["ssl_context"] is context


def test_redis_tls_client_config_without_credentials(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Client:
        connection_pool = None

    def fake_from_url(url: str, **kwargs: Any) -> Any:
        captured["url"] = url
        captured.update(kwargs)
        return _Client()

    redis_module = pytest.importorskip("redis")
    monkeypatch.setattr(redis_module.Redis, "from_url", fake_from_url)
    monkeypatch.setattr("core.data.feature_store.redis", redis_module, raising=False)

    config = RedisClientConfig(url="rediss://example.com:6379/0")
    client = config.create_client()
    assert isinstance(client, _Client)
    assert captured["url"] == "rediss://example.com:6379/0"
    assert "username" not in captured
    assert "password" not in captured


def test_redis_tls_url_required(monkeypatch) -> None:
    monkeypatch.setattr("core.data.feature_store.redis", object(), raising=False)
    with pytest.raises(FeatureStoreConfigurationError):
        RedisClientConfig(url="redis://example.com:6379/0").create_client()


def test_redis_sync_detects_column_mismatch(sample_frame: pd.DataFrame) -> None:
    store = RedisOnlineFeatureStore()
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    mismatched = sample_frame.assign(extra=1)
    with pytest.raises(ValueError):
        store.sync("demo.view", mismatched, mode="append", validate=False)


def test_redis_client_tls_detection_handles_non_dict_pool() -> None:
    class _Client:
        connection_pool = type("Pool", (), {"connection_kwargs": ["not", "dict"]})()

    assert _redis_client_uses_tls(_Client()) is True


def test_redis_client_tls_detection_accepts_tls_flags() -> None:
    class _Client:
        connection_pool = type("Pool", (), {"connection_kwargs": {"ssl": True}})()

    assert _redis_client_uses_tls(_Client()) is True


def test_redis_online_store_rejects_conflicting_client_arguments() -> None:
    class _StubConfig:
        def create_client(self) -> KeyValueClient:
            return InMemoryKeyValueClient()

    with pytest.raises(FeatureStoreConfigurationError):
        RedisOnlineFeatureStore(
            client=InMemoryKeyValueClient(), client_config=_StubConfig()
        )


def test_redis_sync_orders_columns_for_append(sample_frame: pd.DataFrame) -> None:
    store = RedisOnlineFeatureStore()
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    reordered = sample_frame.loc[:, ["value", "entity_id", "ts"]]
    report = store.sync("demo.view", reordered, mode="append", validate=False)
    assert report.offline_rows == reordered.shape[0]


def test_redis_sync_empty_append_returns_empty_delta(
    sample_frame: pd.DataFrame,
) -> None:
    store = RedisOnlineFeatureStore()
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    empty = sample_frame.iloc[0:0]
    report = store.sync("demo.view", empty, mode="append", validate=False)
    assert report.offline_rows == 0
    assert report.online_rows == 0


def test_redis_append_without_existing(sample_frame: pd.DataFrame) -> None:
    store = RedisOnlineFeatureStore()
    report = store.sync("demo.view", sample_frame, mode="append", validate=False)
    assert report.offline_rows == sample_frame.shape[0]


def test_redis_load_missing_returns_empty() -> None:
    store = RedisOnlineFeatureStore()
    result = store.load("unknown")
    assert result.empty


def test_redis_load_applies_retention_and_persists() -> None:
    client = _TrackingClient()
    clock = _TestClock(pd.Timestamp("2024-01-01T01:00:00", tz=UTC))
    policy = RetentionPolicy(ttl=pd.Timedelta(minutes=10))
    store = RedisOnlineFeatureStore(
        client=client, retention_policy=policy, clock=clock.now
    )
    frame = pd.DataFrame(
        {
            "entity_id": ["a", "b"],
            "ts": [
                clock.now() - pd.Timedelta(minutes=15),
                clock.now() - pd.Timedelta(minutes=5),
            ],
            "value": [1.0, 2.0],
        }
    )
    store.sync("demo.view", frame, mode="overwrite", validate=False)
    clock.advance(pd.Timedelta(minutes=15))
    trimmed = store.load("demo.view")
    assert trimmed.empty
    assert len(client.calls) >= 2


def test_redis_purge_removes_payload(sample_frame: pd.DataFrame) -> None:
    store = RedisOnlineFeatureStore()
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    store.purge("demo.view")
    assert store.load("demo.view").empty


def test_integrity_report_detects_mismatches() -> None:
    report = IntegrityReport(
        feature_view="demo",
        offline_rows=2,
        online_rows=3,
        row_count_diff=1,
        offline_hash="abc",
        online_hash="def",
        hash_differs=True,
    )
    with pytest.raises(FeatureStoreIntegrityError):
        report.ensure_valid()


@pytest.mark.parametrize(
    "value,expected",
    [
        (math.nan, "NaN"),
        (pd.NA, "NaN"),
        ("NaN", "NaN"),
        (math.inf, "Infinity"),
        (-math.inf, "-Infinity"),
        (Fraction(1, 3), "0.3333333333333333"),
        (Decimal("NaN"), "NaN"),
        (Decimal("Infinity"), "Infinity"),
        (Decimal("-Infinity"), "-Infinity"),
        (Decimal("0.000"), "0"),
        ("not-a-number", "not-a-number"),
    ],
)
def test_format_numeric_value(value, expected) -> None:
    assert _format_numeric_value(value) == expected


def test_format_numeric_value_handles_decimal_strings() -> None:
    assert _format_numeric_value("1.2300") == "1.23"


def test_normalize_for_hash_coerces_types(tmp_path: Path) -> None:
    store = OnlineFeatureStore(tmp_path)
    frame = pd.DataFrame(
        {
            "ts": ["2024-01-01T00:00:00Z"],
            "duration": [pd.Timedelta(seconds=30)],
            "numeric_str": ["3.000"],
            "category": ["alpha"],
        }
    )
    normalized = store._normalize_for_hash(frame)
    assert str(normalized.loc[0, "numeric_str"]) == "3"
    assert normalized.loc[0, "duration"] == "0 days 00:00:30"
    assert normalized.loc[0, "category"] == "alpha"
    assert pd.api.types.is_datetime64_any_dtype(normalized["ts"])


def test_normalize_for_hash_handles_categorical(tmp_path: Path) -> None:
    store = OnlineFeatureStore(tmp_path)
    frame = pd.DataFrame({"category": pd.Categorical(["one", "two"])})
    normalized = store._normalize_for_hash(frame)
    assert list(normalized["category"]) == ["one", "two"]


def test_online_store_append_concatenates_and_validates(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    store = OnlineFeatureStore(tmp_path)
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    additional = sample_frame.copy()
    additional.loc[:, "ts"] = additional["ts"] + pd.Timedelta(minutes=10)
    report = store.sync("demo.view", additional, mode="append", validate=False)
    assert report.offline_rows == additional.shape[0]
    assert report.hash_differs is False


def test_online_store_append_without_existing(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    store = OnlineFeatureStore(tmp_path)
    report = store.sync("demo.view", sample_frame, mode="append", validate=False)
    assert report.offline_rows == sample_frame.shape[0]


def test_online_store_append_frames_handles_empty(sample_frame: pd.DataFrame) -> None:
    empty = pd.DataFrame(columns=sample_frame.columns)
    appended = OnlineFeatureStore._append_frames(empty, sample_frame)
    pd.testing.assert_frame_equal(appended, sample_frame.reset_index(drop=True))


def test_online_store_canonicalize_with_no_columns() -> None:
    frame = pd.DataFrame(index=[0, 1])
    canonical = OnlineFeatureStore._canonicalize(frame)
    assert canonical.empty


def test_online_store_canonicalize_orders_columns() -> None:
    frame = pd.DataFrame({"b": [2, 1], "a": [1, 2]}, index=[5, 3])
    canonical = OnlineFeatureStore._canonicalize(frame)
    assert list(canonical.columns) == ["a", "b"]
    assert list(canonical.index) == [0, 1]
    assert canonical.loc[0, "a"] == 1


def test_online_store_sync_rejects_mismatched_columns(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    store = OnlineFeatureStore(tmp_path)
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    with pytest.raises(ValueError):
        store.sync(
            "demo.view", sample_frame.assign(extra=1), mode="append", validate=False
        )


def test_online_store_sync_rejects_invalid_mode(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    store = OnlineFeatureStore(tmp_path)
    with pytest.raises(ValueError, match="mode"):
        store.sync("demo.view", sample_frame, mode="invalid", validate=False)  # type: ignore[arg-type]


def test_online_store_append_empty_delta(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    store = OnlineFeatureStore(tmp_path)
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    empty = sample_frame.iloc[0:0]
    report = store.sync("demo.view", empty, mode="append", validate=False)
    assert report.online_rows == 0


def test_online_store_purge_removes_artifacts(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    store = OnlineFeatureStore(tmp_path)
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    assert store.load("demo.view").empty is False
    store.purge("demo.view")
    assert store.load("demo.view").empty


def test_online_store_write_frame_copies_legacy_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = OnlineFeatureStore(tmp_path)
    feature_view = "demo.view"
    destination = store._resolve_path(feature_view)
    target_path = destination.with_suffix(".json")
    index_path = destination.with_suffix(".index.json")
    names_path = destination.with_suffix(".index.names.json")

    def fake_write_dataframe(
        frame: pd.DataFrame, dest: Path, *, index: bool, allow_json_fallback: bool
    ) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("data")
        index_path.write_text("index")
        names_path.write_text("names")
        return target_path

    monkeypatch.setattr("core.data.feature_store.write_dataframe", fake_write_dataframe)

    frame = pd.DataFrame({"value": [1, 2]})
    store._write_frame(feature_view, destination, frame)

    legacy_base = tmp_path / feature_view
    assert legacy_base.with_suffix(".json").read_text() == "data"
    assert legacy_base.with_suffix(".index.json").read_text() == "index"
    assert legacy_base.with_suffix(".index.names.json").read_text() == "names"


def test_sqlite_store_purge_and_missing_load(
    tmp_path: Path,
    sample_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db", encryption=sqlite_encryption_config
    )
    assert store.load("missing").empty
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    store.purge("demo.view")
    assert store.load("demo.view").empty


def test_sqlite_load_reapplies_retention_and_persists(
    tmp_path: Path,
    sample_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    clock = _TestClock(pd.Timestamp("2024-01-01T12:00:00", tz=UTC))
    policy = RetentionPolicy(ttl=pd.Timedelta(minutes=30))
    store = SQLiteOnlineFeatureStore(
        tmp_path / "retained.db",
        encryption=sqlite_encryption_config,
        retention_policy=policy,
        clock=clock.now,
    )
    historical = sample_frame.copy()
    historical.loc[:, "ts"] = [
        clock.now() - pd.Timedelta(hours=1),
        clock.now() - pd.Timedelta(minutes=10),
    ]
    store.sync("demo.view", historical, mode="overwrite", validate=False)

    recorded: list[pd.DataFrame] = []

    def _capture_persist(name: str, frame: pd.DataFrame) -> None:
        recorded.append(frame.copy())

    store._persist = _capture_persist  # type: ignore[method-assign]
    clock.advance(pd.Timedelta(minutes=60))
    trimmed = store.load("demo.view")

    assert trimmed.empty
    assert recorded and recorded[0].empty


def test_sqlite_sync_rejects_invalid_mode(
    tmp_path: Path,
    sample_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db", encryption=sqlite_encryption_config
    )
    with pytest.raises(ValueError, match="mode"):
        store.sync("demo.view", sample_frame, mode="invalid", validate=False)  # type: ignore[arg-type]


def test_sqlite_append_without_existing(
    tmp_path: Path,
    sample_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db", encryption=sqlite_encryption_config
    )
    report = store.sync("demo.view", sample_frame, mode="append", validate=False)
    assert report.offline_rows == sample_frame.shape[0]


def test_sqlite_append_empty_delta(
    tmp_path: Path,
    sample_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db", encryption=sqlite_encryption_config
    )
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    empty = sample_frame.iloc[0:0]
    report = store.sync("demo.view", empty, mode="append", validate=False)
    assert report.online_rows == 0


def test_sqlite_store_requires_encryption(tmp_path: Path) -> None:
    with pytest.raises(FeatureStoreConfigurationError):
        SQLiteOnlineFeatureStore(tmp_path / "store.db", encryption=None)  # type: ignore[arg-type]


def test_sqlite_envelope_plaintext_handling() -> None:
    strict = _SQLiteEncryptionEnvelope(
        SQLiteEncryptionConfig(key_id="v1", key_material="alpha")
    )
    with pytest.raises(FeatureStoreConfigurationError):
        strict.decrypt(b"plaintext")

    permissive = _SQLiteEncryptionEnvelope(
        SQLiteEncryptionConfig(
            key_id="v1",
            key_material="alpha",
            allow_plaintext_fallback=True,
        )
    )
    assert permissive.decrypt(b"plaintext") == b"plaintext"


def test_sqlite_envelope_validates_structure() -> None:
    envelope = _SQLiteEncryptionEnvelope(
        SQLiteEncryptionConfig(key_id="v1", key_material="alpha")
    )

    with pytest.raises(FeatureStoreConfigurationError, match="header is truncated"):
        envelope.decrypt(_ENVELOPE_PREFIX)

    with pytest.raises(FeatureStoreConfigurationError, match="missing key identifier"):
        envelope.decrypt(_ENVELOPE_PREFIX + bytes([1]))

    with pytest.raises(FeatureStoreConfigurationError, match="missing nonce"):
        envelope.decrypt(_ENVELOPE_PREFIX + bytes([1]) + b"a")


def test_sqlite_envelope_unknown_key_identifier() -> None:
    envelope = _SQLiteEncryptionEnvelope(
        SQLiteEncryptionConfig(key_id="v1", key_material="alpha")
    )
    payload = envelope.encrypt(b"secret")
    header_len = len(_ENVELOPE_PREFIX)
    key_len = payload[header_len]
    cursor = header_len + 1 + key_len
    forged = _ENVELOPE_PREFIX + bytes([1]) + b"x" + payload[cursor:]
    with pytest.raises(FeatureStoreConfigurationError):
        envelope.decrypt(forged)


def test_sqlite_payload_is_encrypted(
    tmp_path: Path,
    sample_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db", encryption=sqlite_encryption_config
    )
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)
    with sqlite3.connect(tmp_path / "store.db") as connection:
        payload = connection.execute(
            "SELECT payload FROM feature_views WHERE name = ?",
            ("demo.view",),
        ).fetchone()[0]
    assert isinstance(payload, bytes)
    assert payload.startswith(b"TPENC1")


def test_sqlite_store_fallback_key(
    tmp_path: Path,
    sample_frame: pd.DataFrame,
    sqlite_encryption_config: SQLiteEncryptionConfig,
) -> None:
    store = SQLiteOnlineFeatureStore(
        tmp_path / "store.db", encryption=sqlite_encryption_config
    )
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)

    rotated = SQLiteEncryptionConfig(
        key_id="v2",
        key_material="rotated-secret",
        fallback_keys={"v1": "primary-secret"},
    )
    reopened = SQLiteOnlineFeatureStore(tmp_path / "store.db", encryption=rotated)
    loaded = reopened.load("demo.view")
    assert not loaded.empty


def test_sqlite_reencrypt_payloads(tmp_path: Path, sample_frame: pd.DataFrame) -> None:
    original = SQLiteEncryptionConfig(key_id="v1", key_material="alpha")
    rotated = SQLiteEncryptionConfig(key_id="v2", key_material="beta")
    store = SQLiteOnlineFeatureStore(tmp_path / "store.db", encryption=original)
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)

    reencrypt_sqlite_payloads(
        tmp_path / "store.db",
        current_encryption=original,
        target_encryption=rotated,
        backup=False,
    )

    reopened = SQLiteOnlineFeatureStore(tmp_path / "store.db", encryption=rotated)
    loaded = reopened.load("demo.view")
    pd.testing.assert_frame_equal(loaded, sample_frame.reset_index(drop=True))


def test_sqlite_reencrypt_from_plaintext(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    path = tmp_path / "store.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS feature_views (name TEXT PRIMARY KEY, payload BLOB)"
        )
        payload = _table_orient_payload(sample_frame)
        connection.execute(
            "REPLACE INTO feature_views (name, payload) VALUES (?, ?)",
            ("demo.view", payload),
        )

    rotated = SQLiteEncryptionConfig(key_id="v2", key_material="beta")
    reencrypt_sqlite_payloads(
        path,
        current_encryption=None,
        target_encryption=rotated,
        backup=False,
    )

    reopened = SQLiteOnlineFeatureStore(path, encryption=rotated)
    loaded = reopened.load("demo.view")
    pd.testing.assert_frame_equal(loaded, sample_frame.reset_index(drop=True))


def test_sqlite_reencrypt_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        reencrypt_sqlite_payloads(
            target,
            current_encryption=None,
            target_encryption=SQLiteEncryptionConfig(key_id="v1", key_material="alpha"),
        )


def test_sqlite_reencrypt_creates_backup(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    original = SQLiteEncryptionConfig(key_id="v1", key_material="alpha")
    rotated = SQLiteEncryptionConfig(key_id="v2", key_material="beta")
    path = tmp_path / "store.db"
    store = SQLiteOnlineFeatureStore(path, encryption=original)
    store.sync("demo.view", sample_frame, mode="overwrite", validate=False)

    reencrypt_sqlite_payloads(
        path,
        current_encryption=original,
        target_encryption=rotated,
        backup=True,
    )

    backup_path = path.with_suffix(path.suffix + ".bak")
    assert backup_path.exists()


def test_sqlite_reencrypt_rejects_non_bytes_payload(tmp_path: Path) -> None:
    path = tmp_path / "store.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS feature_views (name TEXT PRIMARY KEY, payload BLOB)"
        )
        connection.execute(
            "REPLACE INTO feature_views (name, payload) VALUES (?, ?)",
            ("demo.view", "not-bytes"),
        )

    with pytest.raises(FeatureStoreConfigurationError):
        reencrypt_sqlite_payloads(
            path,
            current_encryption=None,
            target_encryption=SQLiteEncryptionConfig(key_id="v1", key_material="alpha"),
            backup=False,
        )


def test_offline_validator_non_enforcing(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    offline_path = tmp_path / "offline"
    write_dataframe(sample_frame, offline_path, allow_json_fallback=True)
    validator = OfflineStoreValidator(
        "demo.view",
        DeltaLakeSource(offline_path),
        lambda _name: sample_frame,
        interval=pd.Timedelta(minutes=5),
        clock=lambda: pd.Timestamp("2024-01-01T00:00:00", tz=UTC),
    )
    report = validator.run(enforce=False)
    assert report.hash_differs is False


def test_offline_validator_rejects_non_positive_interval(
    sample_frame: pd.DataFrame,
) -> None:
    source = _FrameSource(sample_frame)
    with pytest.raises(ValueError, match="interval"):
        OfflineStoreValidator(
            "demo.view",
            source,
            lambda _name: sample_frame,
            interval=pd.Timedelta(0),
        )


def test_delta_and_iceberg_sources_roundtrip(
    tmp_path: Path, sample_frame: pd.DataFrame
) -> None:
    delta_path = tmp_path / "delta"
    iceberg_path = tmp_path / "iceberg"
    write_dataframe(sample_frame, delta_path, allow_json_fallback=True)
    write_dataframe(sample_frame, iceberg_path, allow_json_fallback=True)
    delta_frame = DeltaLakeSource(delta_path).load()
    iceberg_frame = IcebergSource(iceberg_path).load()
    expected = sample_frame.reset_index(drop=True)
    assert list(delta_frame.columns) == list(expected.columns)
    assert list(iceberg_frame.columns) == list(expected.columns)
    pd.testing.assert_series_equal(
        pd.to_datetime(delta_frame["ts"], utc=True).reset_index(drop=True),
        expected["ts"],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        pd.to_datetime(iceberg_frame["ts"], utc=True).reset_index(drop=True),
        expected["ts"],
        check_names=False,
    )
    assert delta_frame["entity_id"].tolist() == expected["entity_id"].tolist()
    assert iceberg_frame["entity_id"].tolist() == expected["entity_id"].tolist()
    assert delta_frame["value"].tolist() == expected["value"].tolist()
    assert iceberg_frame["value"].tolist() == expected["value"].tolist()
