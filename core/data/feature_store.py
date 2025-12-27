"""Online feature store helpers with integrity and retention utilities."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import shutil
import sqlite3
import ssl
from dataclasses import dataclass, field
from datetime import UTC
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol
from urllib.parse import urlparse

import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pandas.api import types as pd_types

if not hasattr(pd, "_pandas_datetime_CAPI"):  # pragma: no cover - runtime shim
    pd._pandas_datetime_CAPI = None

from core.utils.dataframe_io import (
    purge_dataframe_artifacts,
    read_dataframe,
    write_dataframe,
)

try:  # pragma: no cover - optional dependency shim for real Redis connections
    import redis
except Exception:  # pragma: no cover - redis is optional during testing
    redis = None  # type: ignore[assignment]


class FeatureStoreIntegrityError(RuntimeError):
    """Raised when integrity invariants fail for feature store payloads."""


class FeatureStoreConfigurationError(RuntimeError):
    """Raised when feature store configuration violates security requirements."""


@dataclass(frozen=True)
class RetentionPolicy:
    """Configuration for expiring historical feature values."""

    ttl: pd.Timedelta | None = None
    max_versions: int | None = None

    def __post_init__(self) -> None:
        if self.ttl is not None and self.ttl <= pd.Timedelta(0):
            raise ValueError("ttl must be positive when provided")
        if self.max_versions is not None and self.max_versions <= 0:
            raise ValueError("max_versions must be positive when provided")


class _RetentionManager:
    """Apply retention rules to pandas dataframes."""

    def __init__(
        self,
        policy: RetentionPolicy | None,
        *,
        clock: Callable[[], pd.Timestamp] | None = None,
    ) -> None:
        self._policy = policy
        self._clock = clock or (lambda: pd.Timestamp.now(tz=UTC))

    def apply(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or self._policy is None:
            return frame.copy()

        result = frame.copy()

        if self._policy.ttl is not None:
            if "ts" not in result.columns:
                raise KeyError("Retention policy with ttl requires a 'ts' column")
            result["ts"] = pd.to_datetime(result["ts"], utc=True, errors="raise")
            cutoff = self._clock() - self._policy.ttl
            result = result[result["ts"] >= cutoff]

        if self._policy.max_versions is not None:
            missing = {"entity_id", "ts"} - set(result.columns)
            if missing:
                joined = ", ".join(sorted(missing))
                raise KeyError(
                    "Retention policy with max_versions requires columns: " f"{joined}"
                )
            ordered = result.sort_values(by=["entity_id", "ts"], kind="mergesort")
            limited = ordered.groupby("entity_id", as_index=False).tail(
                self._policy.max_versions
            )
            result = limited.sort_values(by=["entity_id", "ts"], kind="mergesort")

        return result.reset_index(drop=True)

    def ttl_seconds(self) -> int | None:
        """Return the configured TTL in whole seconds if one has been set."""

        if self._policy is None or self._policy.ttl is None:
            return None

        total_seconds = self._policy.ttl.total_seconds()
        if (
            total_seconds <= 0
        ):  # pragma: no cover - RetentionPolicy enforces positive TTL
            return None

        return max(1, math.ceil(total_seconds))


class KeyValueClient(Protocol):
    """Minimal protocol for key-value stores such as Redis."""

    def get(self, key: str) -> bytes | None: ...

    def set(self, key: str, value: bytes) -> None: ...

    def delete(self, key: str) -> None: ...


class InMemoryKeyValueClient:
    """In-memory key-value client used for tests and local development."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:  # pragma: no cover - trivial
        return self._store.get(key)

    def set(self, key: str, value: bytes) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


def _serialize_frame(frame: pd.DataFrame) -> bytes:
    """Serialize a dataframe to bytes using a safe JSON representation."""

    if frame.empty:
        return b""

    def _encode(value: Any) -> Any:
        if pd.isna(value):
            return None
        formatter = getattr(value, "isoformat", None)
        if callable(formatter):
            try:
                return formatter()
            except Exception:
                pass
        return value

    columns = list(frame.columns)
    dtypes = [str(frame[col].dtype) for col in columns]
    data = [
        [_encode(item) for item in row]
        for row in frame.itertuples(index=False, name=None)
    ]

    payload = json.dumps(
        {"columns": columns, "dtypes": dtypes, "data": data},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return payload.encode("utf-8")


def _deserialize_frame(payload: bytes) -> pd.DataFrame:
    """Deserialize a dataframe from the JSON representation used in storage."""

    if not payload:
        return pd.DataFrame()
    text = payload.decode("utf-8")
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return pd.DataFrame()

    # Legacy "table" orient payloads include a schema key; delegate to pandas.
    if isinstance(decoded, dict) and "schema" in decoded and "data" in decoded:
        return pd.read_json(StringIO(text), orient="table")

    columns: list[str] = decoded.get("columns", [])
    dtypes: list[str] = decoded.get("dtypes", [])
    data = decoded.get("data", [])

    frame = pd.DataFrame(data=data, columns=columns)

    for column, dtype_str in zip(columns, dtypes):
        if dtype_str.startswith("datetime64"):
            frame[column] = pd.to_datetime(frame[column], utc="UTC" in dtype_str)
            continue
        if dtype_str.startswith("timedelta64"):
            frame[column] = pd.to_timedelta(frame[column])
            continue
        if dtype_str != "object":
            try:
                frame[column] = frame[column].astype(dtype_str)
            except (TypeError, ValueError):
                continue

    return frame


@dataclass(frozen=True)
class RedisClientConfig:
    """Configuration for creating TLS-enabled Redis clients."""

    url: str
    username: str | None = None
    password: str | None = None
    ssl_context: ssl.SSLContext | None = None

    def create_client(self) -> KeyValueClient:
        """Instantiate a Redis client enforcing TLS connectivity."""

        parsed = urlparse(self.url)
        if parsed.scheme != "rediss":
            raise FeatureStoreConfigurationError(
                "Redis client URLs must use rediss:// when TLS is required"
            )

        if redis is None:  # pragma: no cover - executed only without redis dependency
            raise FeatureStoreConfigurationError(
                "redis package is required to build TLS-enabled clients"
            )

        context = self.ssl_context or ssl.create_default_context()
        kwargs: dict[str, Any] = {"ssl_context": context}
        if self.username is not None:
            kwargs["username"] = self.username
        if self.password is not None:
            kwargs["password"] = self.password
        return redis.Redis.from_url(self.url, **kwargs)


def _redis_client_uses_tls(client: KeyValueClient) -> bool:
    """Best-effort detection to confirm that a Redis client is TLS-enabled."""

    pool = getattr(client, "connection_pool", None)
    if pool is None:
        return True

    connection_kwargs = getattr(pool, "connection_kwargs", None)
    if not isinstance(connection_kwargs, dict):
        return True

    if connection_kwargs.get("ssl") or connection_kwargs.get("ssl_context"):
        return True

    return False


class RedisOnlineFeatureStore:
    """Redis-backed feature store with TTL-aware retention policies."""

    def __init__(
        self,
        client: KeyValueClient | None = None,
        *,
        client_config: RedisClientConfig | None = None,
        retention_policy: RetentionPolicy | None = None,
        clock: Callable[[], pd.Timestamp] | None = None,
    ) -> None:
        if client is not None and client_config is not None:
            raise FeatureStoreConfigurationError(
                "Provide either a Redis client or a TLS client configuration, not both"
            )

        if client_config is not None:
            self._client = client_config.create_client()
        elif client is not None:
            if not _redis_client_uses_tls(client):
                raise FeatureStoreConfigurationError(
                    "Redis clients must be configured with TLS. Provide a rediss:// URL "
                    "or an SSL context via RedisClientConfig."
                )
            self._client = client
        else:
            self._client = InMemoryKeyValueClient()
        self._retention = _RetentionManager(retention_policy, clock=clock)

    def purge(self, feature_view: str) -> None:
        self._client.delete(feature_view)

    def load(self, feature_view: str) -> pd.DataFrame:
        payload = self._client.get(feature_view)
        if payload is None:
            return pd.DataFrame()
        frame = _deserialize_frame(payload)
        retained = self._retention.apply(frame)
        if not retained.equals(frame):
            self._persist(feature_view, retained)
        return retained

    def sync(
        self,
        feature_view: str,
        frame: pd.DataFrame,
        *,
        mode: Literal["append", "overwrite"] = "append",
        validate: bool = True,
    ) -> "IntegrityReport":
        if mode not in {"append", "overwrite"}:
            raise ValueError("mode must be either 'append' or 'overwrite'")

        offline_frame = frame.copy(deep=True)

        if mode == "overwrite":
            stored = self._write(feature_view, offline_frame)
            report = OnlineFeatureStore._build_report(
                feature_view, offline_frame, stored
            )
        else:
            existing = self.load(feature_view)
            if not existing.empty:
                missing = set(existing.columns) ^ set(offline_frame.columns)
                if missing:
                    raise ValueError(
                        "Cannot append payload with mismatched columns: "
                        f"{sorted(missing)}"
                    )
                offline_frame = offline_frame[existing.columns]
                combined = OnlineFeatureStore._append_frames(existing, offline_frame)
            else:
                combined = offline_frame.reset_index(drop=True)
            stored = self._write(feature_view, combined)
            delta_rows = offline_frame.shape[0]
            if delta_rows:
                online_delta = stored.tail(delta_rows).reset_index(drop=True)
            else:
                online_delta = stored.iloc[0:0]
            report = OnlineFeatureStore._build_report(
                feature_view, offline_frame, online_delta
            )

        if validate:
            report.ensure_valid()
        return report

    def _write(self, feature_view: str, frame: pd.DataFrame) -> pd.DataFrame:
        prepared = self._retention.apply(frame)
        self._persist(feature_view, prepared)
        return prepared.reset_index(drop=True)

    def _persist(self, feature_view: str, frame: pd.DataFrame) -> None:
        payload = _serialize_frame(frame)
        ttl_seconds = self._retention.ttl_seconds()
        if ttl_seconds is not None:
            if hasattr(self._client, "setex"):
                self._client.setex(feature_view, ttl_seconds, payload)
                return
            if hasattr(self._client, "set_with_ttl"):
                self._client.set_with_ttl(feature_view, payload, ttl_seconds)
                return
        self._client.set(feature_view, payload)


_ENVELOPE_PREFIX = b"TPENC1"
_NONCE_SIZE = 12


def _derive_aes_key(material: bytes | str) -> bytes:
    """Normalize user-provided key material for AES-GCM usage."""

    if isinstance(material, str):
        material_bytes = material.encode("utf-8")
    else:
        material_bytes = material

    if not material_bytes:
        raise FeatureStoreConfigurationError("Encryption key material cannot be empty")

    if len(material_bytes) in {16, 24, 32}:
        return material_bytes

    return hashlib.sha256(material_bytes).digest()


@dataclass(frozen=True)
class SQLiteEncryptionConfig:
    """Key management configuration for encrypted SQLite payloads."""

    key_id: str
    key_material: bytes | str
    fallback_keys: Mapping[str, bytes | str] = field(default_factory=dict)
    allow_plaintext_fallback: bool = False

    def __post_init__(self) -> None:
        key_id_bytes = self.key_id.encode("utf-8")
        if not key_id_bytes:
            raise ValueError("key_id must be provided for encrypted payloads")
        if len(key_id_bytes) > 255:
            raise ValueError("key_id must not exceed 255 bytes when encoded as UTF-8")

        # Validate fallback key identifiers are within the supported range.
        for fallback_id in self.fallback_keys:
            encoded = fallback_id.encode("utf-8")
            if not encoded:
                raise ValueError("fallback key identifiers cannot be empty")
            if len(encoded) > 255:
                raise ValueError(
                    "fallback key identifiers must not exceed 255 bytes when encoded"
                )


class _SQLiteEncryptionEnvelope:
    """Encrypt and decrypt SQLite payloads with authenticated envelopes."""

    def __init__(self, config: SQLiteEncryptionConfig) -> None:
        self._config = config
        self._primary_key = AESGCM(_derive_aes_key(config.key_material))
        self._key_id_bytes = config.key_id.encode("utf-8")
        self._fallback: dict[str, AESGCM] = {
            key_id: AESGCM(_derive_aes_key(material))
            for key_id, material in config.fallback_keys.items()
        }
        self._allow_plaintext = config.allow_plaintext_fallback

    def encrypt(self, payload: bytes) -> bytes:
        nonce = os.urandom(_NONCE_SIZE)
        ciphertext = self._primary_key.encrypt(nonce, payload, self._key_id_bytes)
        header = (
            _ENVELOPE_PREFIX + bytes([len(self._key_id_bytes)]) + self._key_id_bytes
        )
        return header + nonce + ciphertext

    def decrypt(self, payload: bytes, *, allow_plaintext: bool | None = None) -> bytes:
        allow_plaintext = (
            self._allow_plaintext if allow_plaintext is None else allow_plaintext
        )
        if payload.startswith(_ENVELOPE_PREFIX):
            cursor = len(_ENVELOPE_PREFIX)
            if cursor >= len(payload):
                raise FeatureStoreConfigurationError(
                    "Encrypted payload header is truncated"
                )

            key_id_length = payload[cursor]
            cursor += 1
            key_id_bytes = payload[cursor : cursor + key_id_length]
            if len(key_id_bytes) != key_id_length:
                raise FeatureStoreConfigurationError(
                    "Encrypted payload missing key identifier"
                )
            cursor += key_id_length

            if len(payload) < cursor + _NONCE_SIZE:
                raise FeatureStoreConfigurationError("Encrypted payload missing nonce")
            nonce = payload[cursor : cursor + _NONCE_SIZE]
            ciphertext = payload[cursor + _NONCE_SIZE :]

            key_id = key_id_bytes.decode("utf-8")
            aead = self._resolve_key(key_id)
            try:
                return aead.decrypt(nonce, ciphertext, key_id_bytes)
            except Exception as exc:  # pragma: no cover - cryptography provides context
                raise FeatureStoreConfigurationError(
                    f"Failed to decrypt payload with key identifier {key_id!r}"
                ) from exc

        if allow_plaintext:
            return payload

        raise FeatureStoreConfigurationError(
            "Encountered plaintext payload but encryption keys are mandatory"
        )

    def _resolve_key(self, key_id: str) -> AESGCM:
        if key_id == self._config.key_id:
            return self._primary_key
        fallback = self._fallback.get(key_id)
        if fallback is not None:
            return fallback
        raise FeatureStoreConfigurationError(
            f"No encryption key material available for identifier {key_id!r}"
        )


def reencrypt_sqlite_payloads(
    path: Path,
    *,
    current_encryption: SQLiteEncryptionConfig | None,
    target_encryption: SQLiteEncryptionConfig,
    backup: bool = True,
) -> None:
    """Re-encrypt all payloads stored in the SQLite feature store."""

    db_path = Path(path)
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite feature store {db_path} does not exist")

    if backup:
        backup_path = db_path.with_suffix(db_path.suffix + ".bak")
        shutil.copy2(db_path, backup_path)

    source_envelope = (
        _SQLiteEncryptionEnvelope(current_encryption)
        if current_encryption is not None
        else None
    )
    target_envelope = _SQLiteEncryptionEnvelope(target_encryption)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS feature_views (name TEXT PRIMARY KEY, payload BLOB)"
        )
        cursor = connection.execute("SELECT name, payload FROM feature_views")
        rows = cursor.fetchall()

    transformed: list[tuple[str, bytes]] = []
    for name, payload in rows:
        if not isinstance(payload, (bytes, bytearray)):
            raise FeatureStoreConfigurationError(
                "Stored payload must be bytes for migration"
            )
        raw: bytes
        if source_envelope is None:
            raw = bytes(payload)
        else:
            raw = source_envelope.decrypt(bytes(payload))
        transformed.append((name, target_envelope.encrypt(raw)))

    with sqlite3.connect(db_path) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS feature_views (name TEXT PRIMARY KEY, payload BLOB)"
            )
            connection.executemany(
                "REPLACE INTO feature_views (name, payload) VALUES (?, ?)",
                transformed,
            )


class SQLiteOnlineFeatureStore:
    """SQLite-backed online feature store with retention controls."""

    def __init__(
        self,
        path: Path,
        *,
        encryption: "SQLiteEncryptionConfig",
        retention_policy: RetentionPolicy | None = None,
        clock: Callable[[], pd.Timestamp] | None = None,
    ) -> None:
        if encryption is None:
            raise FeatureStoreConfigurationError(
                "SQLiteOnlineFeatureStore requires encryption key material"
            )
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._encryption = _SQLiteEncryptionEnvelope(encryption)
        self._connection = sqlite3.connect(self._path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS feature_views (name TEXT PRIMARY KEY, payload BLOB)"
        )
        self._connection.commit()
        self._retention = _RetentionManager(retention_policy, clock=clock)

    def purge(self, feature_view: str) -> None:
        with self._connection:
            self._connection.execute(
                "DELETE FROM feature_views WHERE name = ?", (feature_view,)
            )

    def load(self, feature_view: str) -> pd.DataFrame:
        cursor = self._connection.execute(
            "SELECT payload FROM feature_views WHERE name = ?", (feature_view,)
        )
        row = cursor.fetchone()
        if row is None:
            return pd.DataFrame()
        decrypted = self._encryption.decrypt(row[0])
        frame = _deserialize_frame(decrypted)
        retained = self._retention.apply(frame)
        if not retained.equals(frame):
            self._persist(feature_view, retained)
        return retained

    def sync(
        self,
        feature_view: str,
        frame: pd.DataFrame,
        *,
        mode: Literal["append", "overwrite"] = "append",
        validate: bool = True,
    ) -> "IntegrityReport":
        if mode not in {"append", "overwrite"}:
            raise ValueError("mode must be either 'append' or 'overwrite'")

        offline_frame = frame.copy(deep=True)

        if mode == "overwrite":
            stored = self._write(feature_view, offline_frame)
            report = OnlineFeatureStore._build_report(
                feature_view, offline_frame, stored
            )
        else:
            existing = self.load(feature_view)
            if not existing.empty:
                missing = set(existing.columns) ^ set(offline_frame.columns)
                if missing:
                    raise ValueError(
                        "Cannot append payload with mismatched columns: "
                        f"{sorted(missing)}"
                    )
                offline_frame = offline_frame[existing.columns]
                combined = OnlineFeatureStore._append_frames(existing, offline_frame)
            else:
                combined = offline_frame.reset_index(drop=True)
            stored = self._write(feature_view, combined)
            delta_rows = offline_frame.shape[0]
            if delta_rows:
                online_delta = stored.tail(delta_rows).reset_index(drop=True)
            else:
                online_delta = stored.iloc[0:0]
            report = OnlineFeatureStore._build_report(
                feature_view, offline_frame, online_delta
            )

        if validate:
            report.ensure_valid()
        return report

    def _write(self, feature_view: str, frame: pd.DataFrame) -> pd.DataFrame:
        prepared = self._retention.apply(frame)
        self._persist(feature_view, prepared)
        return prepared.reset_index(drop=True)

    def _persist(self, feature_view: str, frame: pd.DataFrame) -> None:
        plaintext = _serialize_frame(frame)
        payload = self._encryption.encrypt(plaintext)
        with self._connection:
            self._connection.execute(
                "REPLACE INTO feature_views (name, payload) VALUES (?, ?)",
                (feature_view, payload),
            )


class OfflineTableSource(Protocol):
    """Protocol describing offline tables used as the source of truth."""

    def load(self) -> pd.DataFrame: ...


@dataclass(frozen=True)
class DeltaLakeSource(OfflineTableSource):
    """Offline source backed by a Delta Lake table."""

    path: Path

    def load(self) -> pd.DataFrame:
        return read_dataframe(self.path, allow_json_fallback=True)


@dataclass(frozen=True)
class IcebergSource(OfflineTableSource):
    """Offline source backed by an Apache Iceberg table."""

    path: Path

    def load(self) -> pd.DataFrame:
        return read_dataframe(self.path, allow_json_fallback=True)


class OfflineStoreValidator:
    """Periodically compare online materialisations with the offline source of truth."""

    def __init__(
        self,
        feature_view: str,
        offline_source: OfflineTableSource,
        online_loader: Callable[[str], pd.DataFrame],
        *,
        interval: pd.Timedelta = pd.Timedelta(hours=1),
        clock: Callable[[], pd.Timestamp] | None = None,
    ) -> None:
        if interval <= pd.Timedelta(0):
            raise ValueError("interval must be positive")
        self._feature_view = feature_view
        self._offline_source = offline_source
        self._online_loader = online_loader
        self._interval = interval
        self._clock = clock or (lambda: pd.Timestamp.now(tz=UTC))
        self._last_run: pd.Timestamp | None = None

    def should_run(self) -> bool:
        if self._last_run is None:
            return True
        return self._clock() - self._last_run >= self._interval

    def run(self, *, enforce: bool = True) -> "IntegrityReport":
        offline_frame = self._offline_source.load().copy(deep=True)
        online_frame = self._online_loader(self._feature_view).copy(deep=True)
        report = OnlineFeatureStore._build_report(
            self._feature_view,
            offline_frame,
            online_frame,
        )
        if enforce:
            report.ensure_valid()
        self._last_run = self._clock()
        return report


@dataclass(frozen=True)
class IntegritySnapshot:
    """Compact representation of a dataset used for integrity comparisons."""

    row_count: int
    data_hash: str


@dataclass(frozen=True)
class IntegrityReport:
    """Integrity comparison between the offline payload and persisted store."""

    feature_view: str
    offline_rows: int
    online_rows: int
    row_count_diff: int
    offline_hash: str
    online_hash: str
    hash_differs: bool

    def ensure_valid(self) -> None:
        """Raise :class:`FeatureStoreIntegrityError` when invariants are violated."""

        if self.row_count_diff != 0:
            raise FeatureStoreIntegrityError(
                f"Row count mismatch for {self.feature_view!r}: "
                f"offline={self.offline_rows}, online={self.online_rows}"
            )
        if self.hash_differs:
            raise FeatureStoreIntegrityError(
                f"Hash mismatch for {self.feature_view!r}: "
                f"offline={self.offline_hash}, online={self.online_hash}"
            )


def _format_numeric_value(value: Any) -> str:
    """Return a normalized string representation for numeric comparisons."""

    if pd.isna(value):
        return "NaN"

    text = str(value)
    try:
        decimal_value = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        try:
            decimal_value = Decimal(str(float(value)))
        except (InvalidOperation, ValueError, TypeError):
            return text

    if decimal_value.is_nan():
        return "NaN"
    if decimal_value.is_infinite():
        return "Infinity" if decimal_value > 0 else "-Infinity"

    normalized = decimal_value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


class OnlineFeatureStore:
    """Simple parquet-backed store providing overwrite/append semantics."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, feature_view: str) -> Path:
        safe_name = feature_view.replace("/", "__").replace(".", "__")
        return self._root / safe_name

    def purge(self, feature_view: str) -> None:
        """Remove persisted artefacts for ``feature_view`` if they exist."""

        path = self._resolve_path(feature_view)
        purge_dataframe_artifacts(path)
        legacy_base = self._root / feature_view
        purge_dataframe_artifacts(legacy_base)

    def load(self, feature_view: str) -> pd.DataFrame:
        """Load the persisted dataframe for ``feature_view``."""

        path = self._resolve_path(feature_view)
        frame = read_dataframe(path, allow_json_fallback=True)
        if "ts" in frame.columns:
            frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
        return frame

    def sync(
        self,
        feature_view: str,
        frame: pd.DataFrame,
        *,
        mode: Literal["append", "overwrite"] = "append",
        validate: bool = True,
    ) -> IntegrityReport:
        """Persist ``frame`` and return an integrity report."""

        if mode not in {"append", "overwrite"}:
            raise ValueError("mode must be either 'append' or 'overwrite'")

        offline_frame = frame.copy(deep=True)
        path = self._resolve_path(feature_view)

        if mode == "overwrite":
            self.purge(feature_view)
            stored = self._write_frame(feature_view, path, offline_frame)
            report = self._build_report(feature_view, offline_frame, stored)
        else:
            existing = self.load(feature_view)
            if not existing.empty:
                missing = set(existing.columns) ^ set(offline_frame.columns)
                if missing:
                    raise ValueError(
                        "Cannot append payload with mismatched columns: "
                        f"{sorted(missing)}"
                    )
                offline_frame = offline_frame[existing.columns]
            stored = self._append_frames(existing, offline_frame)
            self._write_frame(feature_view, path, stored)
            delta_rows = offline_frame.shape[0]
            if delta_rows:
                online_delta = stored.tail(delta_rows).reset_index(drop=True)
            else:
                online_delta = stored.iloc[0:0]
            report = self._build_report(feature_view, offline_frame, online_delta)

        if validate:
            report.ensure_valid()
        return report

    def compute_integrity(
        self, feature_view: str, frame: pd.DataFrame
    ) -> IntegrityReport:
        """Compare ``frame`` against the currently persisted dataset."""

        online = self.load(feature_view)
        return self._build_report(feature_view, frame.copy(deep=True), online)

    @staticmethod
    def _append_frames(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
        if existing.empty:
            return incoming.reset_index(drop=True)
        combined = pd.concat(
            [existing.reset_index(drop=True), incoming.reset_index(drop=True)],
            ignore_index=True,
        )
        return combined

    def _write_frame(
        self, feature_view: str, path: Path, frame: pd.DataFrame
    ) -> pd.DataFrame:
        prepared = frame.reset_index(drop=True)
        written = write_dataframe(prepared, path, index=False, allow_json_fallback=True)

        legacy_base = self._root / feature_view
        legacy_target = legacy_base.with_suffix(written.suffix)
        if legacy_target != written:
            legacy_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(written, legacy_target)
            index_path = written.with_suffix(".index.json")
            if index_path.exists():
                legacy_index = legacy_target.with_suffix(".index.json")
                shutil.copy2(index_path, legacy_index)
            names_path = written.with_suffix(".index.names.json")
            if names_path.exists():
                legacy_names = legacy_target.with_suffix(".index.names.json")
                shutil.copy2(names_path, legacy_names)
        return prepared

    @staticmethod
    def _build_report(
        feature_view: str,
        offline_frame: pd.DataFrame,
        online_frame: pd.DataFrame,
    ) -> IntegrityReport:
        offline_snapshot = OnlineFeatureStore._snapshot(offline_frame)
        online_snapshot = OnlineFeatureStore._snapshot(online_frame)
        hash_differs = not hmac.compare_digest(
            offline_snapshot.data_hash,
            online_snapshot.data_hash,
        )
        return IntegrityReport(
            feature_view=feature_view,
            offline_rows=offline_snapshot.row_count,
            online_rows=online_snapshot.row_count,
            row_count_diff=online_snapshot.row_count - offline_snapshot.row_count,
            offline_hash=offline_snapshot.data_hash,
            online_hash=online_snapshot.data_hash,
            hash_differs=hash_differs,
        )

    @staticmethod
    def _snapshot(frame: pd.DataFrame) -> IntegritySnapshot:
        canonical = OnlineFeatureStore._canonicalize(frame)
        normalized = OnlineFeatureStore._normalize_for_hash(canonical)
        columns = list(normalized.columns)

        def _encode(value: Any) -> Any:
            if pd.isna(value):
                return None
            iso_formatter = getattr(value, "isoformat", None)
            if callable(iso_formatter):
                try:
                    return iso_formatter()
                except Exception:
                    pass
            return value

        data = [
            [_encode(item) for item in row]
            for row in normalized.itertuples(index=False, name=None)
        ]

        payload = json.dumps(
            {"columns": columns, "data": data},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return IntegritySnapshot(row_count=int(canonical.shape[0]), data_hash=digest)

    @staticmethod
    def _canonicalize(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()
        columns = sorted(frame.columns)
        canonical = frame.loc[:, columns].copy()
        if columns:
            canonical = canonical.sort_values(by=columns, kind="mergesort")
        return canonical.reset_index(drop=True)

    @staticmethod
    def _normalize_for_hash(frame: pd.DataFrame) -> pd.DataFrame:
        """Coerce values into stable types prior to hashing."""

        if frame.empty:
            return frame.copy()

        normalized = frame.copy()

        for column in normalized.columns:
            series = normalized[column]

            if pd_types.is_datetime64_any_dtype(series):
                normalized[column] = pd.to_datetime(series, utc=True)
                continue

            if pd_types.is_numeric_dtype(series):
                normalized[column] = series.map(_format_numeric_value)
                continue

            if pd_types.is_timedelta64_dtype(series):
                # Represent timedeltas using ISO-8601 duration strings for stability.
                normalized[column] = series.astype("timedelta64[ns]").astype(str)
                continue

            if series.dtype == object:
                # Attempt to coerce datetime-like payloads first.
                try:
                    coerced_datetime = pd.to_datetime(series, utc=True, errors="raise")
                except (TypeError, ValueError):
                    coerced_datetime = None
                if coerced_datetime is not None and pd_types.is_datetime64_any_dtype(
                    coerced_datetime
                ):
                    normalized[column] = coerced_datetime
                    continue

                try:
                    numeric = pd.to_numeric(series, errors="raise")
                except (TypeError, ValueError):
                    numeric = None
                if numeric is not None and pd_types.is_numeric_dtype(numeric):
                    normalized[column] = numeric.map(_format_numeric_value)
                    continue

                normalized[column] = series.astype(str)

        return normalized


__all__ = [
    "DeltaLakeSource",
    "FeatureStoreConfigurationError",
    "FeatureStoreIntegrityError",
    "IcebergSource",
    "InMemoryKeyValueClient",
    "IntegrityReport",
    "IntegritySnapshot",
    "OfflineStoreValidator",
    "OnlineFeatureStore",
    "RedisClientConfig",
    "RedisOnlineFeatureStore",
    "RetentionPolicy",
    "SQLiteEncryptionConfig",
    "SQLiteOnlineFeatureStore",
    "reencrypt_sqlite_payloads",
]
