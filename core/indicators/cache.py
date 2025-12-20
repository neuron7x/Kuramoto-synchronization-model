# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Indicator caching primitives with fingerprinting and incremental backfill.

This module provides a production-grade caching layer tailored for quantitative
indicators.  It supports deterministic cache keys (fingerprints) that blend the
indicator name, configuration parameters, input data hash and the running code
version.  Results are partitioned per timeframe so multi-resolution analytics
can reuse cached computations independently.

Beyond simple memoization, the cache records coverage metadata (time span,
record counts) and exposes an incremental backfill protocol.  Downstream
pipelines can persist the last processed timestamp for every timeframe and
append only the missing data on the next run—mirroring the workflow used in
large research/replay systems (QuantConnect, Backtrader, etc.).
"""

from __future__ import annotations

import builtins
import enum
import functools
import hashlib
import hmac
import importlib
import json
import os
import pickle  # nosec B403 - guarded by restricted unpickler
import shutil
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Callable, Mapping, MutableMapping, Sequence

import numpy as np
import pandas as pd

from core.utils.dataframe_io import read_dataframe, write_dataframe
from core.utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - used only for type checking
    from .multiscale_kuramoto import TimeFrame

_logger = get_logger(__name__)


def _qualified_name(obj: type) -> str:
    return f"{obj.__module__}:{obj.__qualname__}"


def _sorted_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _encode_structure(value: Any) -> Any:
    """Encode arbitrary Python objects into a JSON-friendly payload."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return {"__type__": "pd.Timestamp", "value": value.isoformat()}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": format(value, "f")}
    if isinstance(value, PurePath):
        return {"__type__": "path", "value": str(value)}
    if is_dataclass(value):
        return {
            "__type__": "dataclass",
            "cls": _qualified_name(type(value)),
            "fields": {
                field.name: _encode_structure(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if isinstance(value, enum.Enum):
        return {
            "__type__": "enum",
            "cls": _qualified_name(type(value)),
            "name": value.name,
        }
    if isinstance(value, Mapping):
        encoded_items = [
            (_encode_structure(key), _encode_structure(val))
            for key, val in value.items()
        ]
        encoded_items.sort(key=lambda item: _sorted_json(item[0]))
        return {
            "__type__": "mapping",
            "items": [[key, val] for key, val in encoded_items],
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        kind = type(value).__name__
        encoded_items = [_encode_structure(item) for item in value]
        if isinstance(value, (set, frozenset)):
            encoded_items.sort(key=_sorted_json)
        return {
            "__type__": "sequence",
            "kind": kind,
            "items": encoded_items,
        }
    return {"__type__": "repr", "value": repr(value)}


def _locate(symbol: str) -> type[Any]:
    module_name, _, qualname = symbol.partition(":")
    module = importlib.import_module(module_name)
    attr: Any = module
    for part in qualname.split("."):
        attr = getattr(attr, part)
    return attr


def _decode_structure(payload: Any) -> Any:
    """Decode payloads produced by :func:`_encode_structure`."""

    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    if isinstance(payload, list):
        return [_decode_structure(item) for item in payload]
    if not isinstance(payload, Mapping):
        return payload

    marker = payload.get("__type__")
    if marker == "pd.Timestamp":
        return pd.Timestamp(payload["value"])
    if marker == "datetime":
        return datetime.fromisoformat(payload["value"])
    if marker == "decimal":
        return Decimal(payload["value"])
    if marker == "path":
        return Path(payload["value"])
    if marker == "dataclass":
        cls = _locate(payload["cls"])
        field_values = {
            key: _decode_structure(val) for key, val in payload["fields"].items()
        }
        return cls(**field_values)
    if marker == "enum":
        cls = _locate(payload["cls"])
        return getattr(cls, payload["name"])
    if marker == "mapping":
        return {
            _decode_structure(key): _decode_structure(val)
            for key, val in payload.get("items", [])
        }
    if marker == "sequence":
        kind = payload.get("kind")
        items = [_decode_structure(item) for item in payload.get("items", [])]
        if kind == "tuple":
            return tuple(items)
        if kind == "set":
            return set(items)
        if kind == "frozenset":
            return frozenset(items)
        return items
    if marker == "repr":
        return payload["value"]

    return {str(key): _decode_structure(value) for key, value in payload.items()}


def make_fingerprint(
    indicator_name: str,
    params: Mapping[str, Any],
    data_hash: str,
    code_version: str,
) -> str:
    """Create a deterministic fingerprint for an indicator execution."""

    payload = {
        "indicator": indicator_name,
        "params": _encode_structure(params),
        "data_hash": data_hash,
        "code_version": code_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_input_data(data: Any) -> str:
    """Hash arbitrary indicator input data."""

    if isinstance(data, pd.DataFrame):
        hashed = pd.util.hash_pandas_object(data, index=True).values
        return hashlib.sha256(hashed.tobytes()).hexdigest()
    if isinstance(data, pd.Series):
        hashed = pd.util.hash_pandas_object(data, index=True).values
        return hashlib.sha256(hashed.tobytes()).hexdigest()
    if isinstance(data, np.ndarray):
        arr = np.ascontiguousarray(data)
        return hashlib.sha256(arr.tobytes()).hexdigest()
    if isinstance(data, Mapping):
        normalized = _encode_structure(data)
        raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        normalized = [_encode_structure(item) for item in data]
        raw = json.dumps(normalized, sort_keys=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    normalized = _encode_structure(data)
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_code_version() -> str:
    """Best-effort resolution of the current code version."""

    git_dir = Path(__file__).resolve().parents[2]
    try:
        head = (git_dir / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1]
            ref_path = git_dir / ".git" / ref
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()
        if head:
            return head
    except Exception as exc:  # pragma: no cover - gitless environments
        _logger.debug("Unable to read git HEAD, falling back to VERSION file: %s", exc)

    version_file = git_dir / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()

    return "0.0.0"


@dataclass(slots=True)
class CacheRecord:
    """Materialized cache entry."""

    value: Any
    metadata: Mapping[str, Any]
    fingerprint: str
    coverage_start: datetime | None
    coverage_end: datetime | None
    stored_at: datetime


@dataclass(slots=True)
class BackfillState:
    """Book-keeping for incremental backfill per timeframe."""

    timeframe: str
    last_timestamp: datetime | None
    fingerprint: str | None
    updated_at: datetime
    extras: Mapping[str, Any]


class FileSystemIndicatorCache:
    """Disk-backed cache that stores indicator outputs per timeframe."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        code_version: str | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.code_version = code_version or _resolve_code_version()
        _logger.debug(
            "indicator_cache_initialized",
            root=str(self.root),
            code_version=self.code_version,
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _timeframe_key(timeframe: "TimeFrame | str | None") -> str:
        if timeframe is None:
            return "_global"
        if hasattr(timeframe, "name"):
            return str(getattr(timeframe, "name"))
        return str(timeframe)

    def _entry_dir(self, timeframe: "TimeFrame | str | None", fingerprint: str) -> Path:
        timeframe_dir = self.root / self._timeframe_key(timeframe)
        return timeframe_dir / fingerprint

    # ---------------------------------------------------------------- serialization
    @staticmethod
    def _file_digest(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _serialize(self, directory: Path, value: Any) -> tuple[str, str, str]:
        data_path = directory / "payload"

        def _write_dtypes(sidecar: Path, dtype_map: Mapping[str, str]) -> None:
            try:
                sidecar.write_text(json.dumps(dtype_map, sort_keys=True))
            except (OSError, TypeError, ValueError) as exc:  # pragma: no cover - defensive
                _logger.warning(
                    "indicator_cache_dtypes_sidecar_write_failed",
                    path=str(sidecar),
                    error=str(exc),
                )

        # pandas structures
        if isinstance(value, pd.DataFrame):
            stored_path = write_dataframe(
                value, data_path, index=True, allow_json_fallback=True
            )
            if stored_path.suffix == ".json":
                _write_dtypes(
                    stored_path.with_suffix(".dtypes.json"),
                    {col: str(dtype) for col, dtype in value.dtypes.items()},
                )
            fmt = "parquet" if stored_path.suffix == ".parquet" else "dataframe-json"
            return stored_path.name, fmt, self._file_digest(stored_path)
        if isinstance(value, pd.Series):
            frame = value.to_frame(name=value.name)
            stored_path = write_dataframe(
                frame, data_path, index=True, allow_json_fallback=True
            )
            if stored_path.suffix == ".json":
                _write_dtypes(
                    stored_path.with_suffix(".dtypes.json"),
                    {frame.columns[0]: str(frame.dtypes[0])},
                )
            fmt = "parquet" if stored_path.suffix == ".parquet" else "series-json"
            return stored_path.name, fmt, self._file_digest(stored_path)
        if isinstance(value, np.ndarray):
            file_path = data_path.with_suffix(".npy")
            np.save(file_path, value)
            return file_path.name, "numpy", self._file_digest(file_path)

        file_path = data_path.with_suffix(".json")
        normalized = _encode_structure(value)
        with file_path.open("w", encoding="utf-8") as handle:
            json.dump(normalized, handle, sort_keys=True)
        return file_path.name, "json", self._file_digest(file_path)

    @staticmethod
    def _restricted_unpickle(handle: Any) -> Any:
        class _SafeUnpickler(pickle.Unpickler):
            _SAFE_BUILTINS = {
                "complex",
                "dict",
                "frozenset",
                "list",
                "set",
                "tuple",
                "int",
                "float",
                "bool",
                "str",
                "bytes",
                "bytearray",
                "memoryview",
                "range",
                "slice",
                "NoneType",
            }

            _SAFE_MODULE_PREFIXES = (
                "collections",
                "datetime",
                "decimal",
                "fractions",
                "numpy",
                "pandas",
                "core.indicators",
            )

            _SAFE_MODULES = {
                "uuid",
                "math",
                "statistics",
                "pathlib",
                "types",
            }

            def find_class(self, module: str, name: str) -> Any:
                if module == "builtins" and name in self._SAFE_BUILTINS:
                    return getattr(builtins, name)
                if module in self._SAFE_MODULES:
                    mod = importlib.import_module(module)
                    return getattr(mod, name)
                for prefix in self._SAFE_MODULE_PREFIXES:
                    if module == prefix or module.startswith(f"{prefix}."):
                        mod = importlib.import_module(module)
                        return getattr(mod, name)
                raise pickle.UnpicklingError(
                    f"Attempted to load unsafe module '{module}.{name}' from cache"
                )

        return _SafeUnpickler(handle).load()

    def _deserialize(self, path: Path, fmt: str) -> Any:
        if fmt == "parquet":
            return read_dataframe(path)
        if fmt == "numpy":
            return np.load(path, allow_pickle=False)
        if fmt in {"dataframe-json", "series-json"}:
            frame = pd.read_json(path, orient="split")
            dtypes_path = path.with_suffix(".dtypes.json")
            if dtypes_path.exists():
                try:
                    dtype_map = json.loads(dtypes_path.read_text(encoding="utf-8"))
                    frame = frame.astype(dtype_map)
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    _logger.warning(
                        "indicator_cache_dtypes_restore_failed",
                        path=str(dtypes_path),
                        error=str(exc),
                    )
            if fmt == "series-json":
                series = frame.iloc[:, 0]
                series.name = frame.columns[0]
                return series
            return frame
        if fmt == "json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _decode_structure(payload)
        raise ValueError(f"Unsupported cache format '{fmt}'")

    # ---------------------------------------------------------------- fingerprint
    def fingerprint(
        self,
        indicator_name: str,
        params: Mapping[str, Any],
        data_hash: str,
        *,
        code_version: str | None = None,
    ) -> str:
        return make_fingerprint(
            indicator_name,
            params,
            data_hash,
            code_version or self.code_version,
        )

    # ------------------------------------------------------------------- mutation
    def store(
        self,
        *,
        indicator_name: str,
        params: Mapping[str, Any],
        data_hash: str,
        value: Any,
        timeframe: "TimeFrame | str | None" = None,
        coverage_start: datetime | str | None = None,
        coverage_end: datetime | str | None = None,
        metadata: Mapping[str, Any] | None = None,
        code_version: str | None = None,
    ) -> str:
        """Persist a cache entry and return its fingerprint."""

        fingerprint = self.fingerprint(
            indicator_name,
            params,
            data_hash,
            code_version=code_version,
        )
        directory = self._entry_dir(timeframe, fingerprint)
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)

        data_file, data_format, data_integrity = self._serialize(directory, value)

        payload: MutableMapping[str, Any] = {
            "fingerprint": fingerprint,
            "indicator": indicator_name,
            "params": _encode_structure(params),
            "data_hash": data_hash,
            "code_version": code_version or self.code_version,
            "timeframe": self._timeframe_key(timeframe),
            "data_file": data_file,
            "data_format": data_format,
            "data_integrity": data_integrity,
            "stored_at": datetime.now(UTC).isoformat(),
            "coverage_start": (
                coverage_start.isoformat()
                if isinstance(coverage_start, datetime)
                else coverage_start
            ),
            "coverage_end": (
                coverage_end.isoformat()
                if isinstance(coverage_end, datetime)
                else coverage_end
            ),
            "metadata": _encode_structure(metadata or {}),
        }

        with (directory / "metadata.json").open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)

        _logger.debug(
            "indicator_cache_store",
            indicator=indicator_name,
            timeframe=payload["timeframe"],
            fingerprint=fingerprint,
            coverage_end=payload.get("coverage_end"),
        )
        return fingerprint

    # -------------------------------------------------------------------- retrieval
    def load(
        self,
        *,
        indicator_name: str,
        params: Mapping[str, Any],
        data_hash: str,
        timeframe: "TimeFrame | str | None" = None,
        code_version: str | None = None,
    ) -> CacheRecord | None:
        fingerprint = self.fingerprint(
            indicator_name,
            params,
            data_hash,
            code_version=code_version,
        )
        directory = self._entry_dir(timeframe, fingerprint)
        metadata_path = directory / "metadata.json"
        if not metadata_path.exists():
            return None

        try:
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

        data_path = directory / meta["data_file"]
        if not data_path.exists():
            return None

        expected_integrity = meta.get("data_integrity")
        actual_integrity = self._file_digest(data_path)
        if expected_integrity and not hmac.compare_digest(
            expected_integrity, actual_integrity
        ):
            _logger.warning(
                "indicator_cache_integrity_mismatch",
                path=str(data_path),
                expected=expected_integrity,
                actual=actual_integrity,
            )
            return None

        value = self._deserialize(data_path, meta["data_format"])

        coverage_start = (
            datetime.fromisoformat(meta["coverage_start"])
            if meta.get("coverage_start")
            else None
        )
        coverage_end = (
            datetime.fromisoformat(meta["coverage_end"])
            if meta.get("coverage_end")
            else None
        )
        stored_at = datetime.fromisoformat(meta["stored_at"])

        metadata = _decode_structure(meta.get("metadata", {}))

        return CacheRecord(
            value=value,
            metadata=metadata,
            fingerprint=fingerprint,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            stored_at=stored_at,
        )

    # ---------------------------------------------------------------- backfill API
    def _backfill_path(self, timeframe: "TimeFrame | str") -> Path:
        return self.root / self._timeframe_key(timeframe) / "backfill.json"

    def get_backfill_state(self, timeframe: "TimeFrame | str") -> BackfillState | None:
        path = self._backfill_path(timeframe)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

        last_ts = payload.get("last_timestamp")
        return BackfillState(
            timeframe=self._timeframe_key(timeframe),
            last_timestamp=datetime.fromisoformat(last_ts) if last_ts else None,
            fingerprint=payload.get("fingerprint"),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            extras=_decode_structure(payload.get("extras", {})),
        )

    def update_backfill_state(
        self,
        timeframe: "TimeFrame | str",
        *,
        last_timestamp: datetime | str,
        fingerprint: str | None,
        extras: Mapping[str, Any] | None = None,
    ) -> None:
        timestamp = (
            last_timestamp.isoformat()
            if isinstance(last_timestamp, datetime)
            else str(last_timestamp)
        )
        payload = {
            "timeframe": self._timeframe_key(timeframe),
            "last_timestamp": timestamp,
            "fingerprint": fingerprint,
            "updated_at": datetime.now(UTC).isoformat(),
            "extras": _encode_structure(extras or {}),
        }
        path = self._backfill_path(timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

        _logger.debug(
            "indicator_cache_backfill_update",
            timeframe=payload["timeframe"],
            last_timestamp=payload["last_timestamp"],
        )


def cache_indicator(
    cache: FileSystemIndicatorCache,
    *,
    indicator_name: str | None = None,
    timeframe: "TimeFrame | str | None" = None,
    params_fn: Callable[..., Mapping[str, Any]] | None = None,
    data_fn: Callable[..., Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that transparently caches indicator outputs."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        resolved_name = indicator_name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            params = params_fn(*args, **kwargs) if params_fn else kwargs
            data = (
                data_fn(*args, **kwargs)
                if data_fn
                else (args[0] if args else kwargs.get("data"))
            )
            if data is None:
                raise ValueError(
                    "cache_indicator requires data argument to compute fingerprint"
                )

            data_hash = hash_input_data(data)
            record = cache.load(
                indicator_name=resolved_name,
                params=params,
                data_hash=data_hash,
                timeframe=timeframe,
            )
            if record is not None:
                _logger.debug(
                    "indicator_cache_hit",
                    indicator=resolved_name,
                    timeframe=cache._timeframe_key(timeframe),
                )
                return record.value

            value = fn(*args, **kwargs)
            cache.store(
                indicator_name=resolved_name,
                params=params,
                data_hash=data_hash,
                value=value,
                timeframe=timeframe,
            )
            _logger.debug(
                "indicator_cache_miss",
                indicator=resolved_name,
                timeframe=cache._timeframe_key(timeframe),
            )
            return value

        return wrapper

    return decorator


__all__ = [
    "BackfillState",
    "CacheRecord",
    "FileSystemIndicatorCache",
    "cache_indicator",
    "hash_input_data",
    "make_fingerprint",
]
