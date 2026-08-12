# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for dataframe serialization with optional parquet backends."""

from __future__ import annotations

import importlib
import io
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import pandas as pd

__all__ = [
    "MissingParquetDependencyError",
    "dataframe_to_parquet_bytes",
    "purge_dataframe_artifacts",
    "read_dataframe",
    "write_dataframe",
    "reset_dataframe_io_backends",
]


class MissingParquetDependencyError(RuntimeError):
    """Raised when no parquet-capable backend is available."""


@dataclass(frozen=True)
class _Backend:
    name: str
    suffix: str
    write_fn: Callable[[pd.DataFrame, Path, bool], None]
    read_fn: Callable[[Path], pd.DataFrame]
    to_bytes_fn: Callable[[pd.DataFrame, bool], bytes] | None


_PARQUET_SUFFIX = ".parquet"
_JSON_SUFFIX = ".json"


@lru_cache(maxsize=1)
def _pyarrow_available() -> bool:
    try:
        importlib.import_module("pyarrow")
    except ModuleNotFoundError:
        return False
    return True


@lru_cache(maxsize=1)
def _load_polars() -> object:
    import polars as pl

    return pl


def reset_dataframe_io_backends() -> None:
    """Reset cached backend discovery (useful for tests)."""

    _pyarrow_available.cache_clear()
    _load_polars.cache_clear()


def _pyarrow_backend() -> _Backend:
    def _write(frame: pd.DataFrame, path: Path, index: bool) -> None:
        frame.to_parquet(path, engine="pyarrow", index=index)

    def _read(path: Path) -> pd.DataFrame:
        return pd.read_parquet(path, engine="pyarrow")

    def _to_bytes(frame: pd.DataFrame, index: bool) -> bytes:
        buffer = io.BytesIO()
        frame.to_parquet(buffer, engine="pyarrow", index=index)
        return buffer.getvalue()

    return _Backend("pyarrow", _PARQUET_SUFFIX, _write, _read, _to_bytes)


def _polars_backend() -> _Backend:
    try:
        pl = _load_polars()
    except ModuleNotFoundError as exc:  # pragma: no cover - defensive
        raise MissingParquetDependencyError("polars is not installed") from exc

    def _prepare(frame: pd.DataFrame, index: bool):
        if index:
            payload = frame.reset_index()
        else:
            payload = frame.reset_index(drop=True)
        try:
            return pl.from_pandas(payload)
        except (ImportError, ModuleNotFoundError):
            data = payload.to_dict(orient="list")
            return pl.DataFrame(data, strict=False)

    def _write(frame: pd.DataFrame, path: Path, index: bool) -> None:
        buffer = io.BytesIO()
        _prepare(frame, index).write_parquet(buffer)
        path.write_bytes(buffer.getvalue())

    def _materialize_without_pyarrow(dataset) -> pd.DataFrame:
        """Convert a polars dataframe to pandas without requiring pyarrow."""

        # ``to_dict(as_series=False)`` returns a mapping from column names to
        # python lists and preserves column order, which pandas can ingest
        # without the optional ``pyarrow`` dependency.
        materialized = dataset.to_dict(as_series=False)
        return pd.DataFrame(materialized, columns=list(materialized.keys()))

    def _read(path: Path) -> pd.DataFrame:
        dataset = pl.read_parquet(path)
        try:
            return dataset.to_pandas(use_pyarrow=False)
        except ModuleNotFoundError as exc:
            missing = getattr(exc, "name", None)
            if missing not in (None, "pyarrow"):  # pragma: no cover - defensive
                raise
            return _materialize_without_pyarrow(dataset)

    def _to_bytes(frame: pd.DataFrame, index: bool) -> bytes:
        buffer = io.BytesIO()
        _prepare(frame, index).write_parquet(buffer)
        return buffer.getvalue()

    return _Backend("polars", _PARQUET_SUFFIX, _write, _read, _to_bytes)


def _json_backend() -> _Backend:
    def _encode_value(value):
        if isinstance(value, pd.Timestamp):
            return value.isoformat(timespec="nanoseconds").replace("+00:00", "Z")
        if isinstance(value, pd.Timedelta):
            return value.isoformat()
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                pass
        return value

    def _write(frame: pd.DataFrame, path: Path, index: bool) -> None:
        payload = frame.to_dict(orient="split")
        if not index:
            payload.pop("index", None)
        else:
            payload["index"] = [_encode_value(value) for value in payload.get("index", [])]
        payload["data"] = [
            [_encode_value(value) for value in row] for row in payload.get("data", [])
        ]
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    def _read(path: Path) -> pd.DataFrame:
        return pd.read_json(path, orient="split")

    return _Backend("json", _JSON_SUFFIX, _write, _read, None)


def _available_backends() -> list[_Backend]:
    backends: list[_Backend] = []
    if _pyarrow_available():
        backends.append(_pyarrow_backend())
    try:
        backends.append(_polars_backend())
    except MissingParquetDependencyError:
        pass
    backends.append(_json_backend())
    return backends


def _select_backend(require_parquet: bool, allow_json_fallback: bool) -> _Backend:
    for backend in _available_backends():
        if backend.suffix == _PARQUET_SUFFIX:
            return backend
        if allow_json_fallback and backend.suffix == _JSON_SUFFIX and not require_parquet:
            return backend
    raise MissingParquetDependencyError(
        "No parquet backend available. Install 'geosync[feature_store]' for pyarrow support or install polars."
    )


def _normalize_destination(destination: Path) -> tuple[Path, bool]:
    if destination.suffix:
        base = destination.with_suffix("")
        explicit_suffix = True
    else:
        base = destination
        explicit_suffix = False
    return base, explicit_suffix


def write_dataframe(
    frame: pd.DataFrame,
    destination: Path,
    *,
    index: bool = False,
    allow_json_fallback: bool = False,
) -> Path:
    """Serialize ``frame`` to ``destination`` using the first available backend."""

    base, explicit_suffix = _normalize_destination(destination)
    suffix = destination.suffix.lower() if explicit_suffix else None

    if suffix not in (None, _PARQUET_SUFFIX, _JSON_SUFFIX):
        raise ValueError("Unsupported dataframe suffix. Expected .parquet or .json")

    if suffix == _JSON_SUFFIX:
        backend = _json_backend()
    else:
        require_parquet = suffix == _PARQUET_SUFFIX if suffix else False
        backend = _select_backend(require_parquet, allow_json_fallback)
    target = base.with_suffix(backend.suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    backend.write_fn(frame, target, index)

    index_path = base.with_suffix(".index.json")
    names_path = base.with_suffix(".index.names.json")
    if index and backend.name == "polars":
        index_frame = frame.index.to_frame(index=False)
        _json_backend().write_fn(index_frame, index_path, index=False)
        if isinstance(frame.index, pd.MultiIndex):
            names = list(frame.index.names)
        else:
            names = [frame.index.name]
        names_payload = [name if name is not None else None for name in names]
        names_path.write_text(json.dumps(names_payload))
    else:
        if index_path.exists():
            index_path.unlink()
        if names_path.exists():
            names_path.unlink()
    return target


def _drop_polars_index_columns(frame: pd.DataFrame, index_frame: pd.DataFrame) -> None:
    """Remove duplicate index columns created by the polars parquet round-trip."""

    if index_frame.empty:
        return

    index_series = [
        index_frame.iloc[:, i].reset_index(drop=True) for i in range(index_frame.shape[1])
    ]
    matched_levels: set[int] = set()
    drop_labels: list[str] = []

    # First match columns by the names stored in the index payload.
    for level_idx, level_name in enumerate(index_frame.columns):
        if level_name in frame.columns:
            candidate = frame[level_name].reset_index(drop=True)
            if candidate.equals(index_series[level_idx]):
                drop_labels.append(level_name)
                matched_levels.add(level_idx)

    # Fall back to positional matching for legacy payloads where the column
    # names differ (e.g. ``level_0`` vs ``0`` for unnamed indexes).
    if len(matched_levels) < len(index_series):
        remaining_levels = [idx for idx in range(len(index_series)) if idx not in matched_levels]
        for position, column in enumerate(frame.columns):
            if not remaining_levels or position >= len(index_series):
                break
            if column in drop_labels:
                continue
            candidate = frame.iloc[:, position].reset_index(drop=True)
            level_idx = remaining_levels[0]
            if candidate.equals(index_series[level_idx]):
                drop_labels.append(column)
                remaining_levels.pop(0)

    if drop_labels:
        frame.drop(columns=drop_labels, inplace=True)


def read_dataframe(path: Path, *, allow_json_fallback: bool = False) -> pd.DataFrame:
    """Load a dataframe from ``path`` using the first compatible backend."""

    path = Path(path)
    if path.suffix:
        suffix = path.suffix.lower()
        if suffix == _PARQUET_SUFFIX:
            backend_name = None
            if _pyarrow_available():
                frame = _pyarrow_backend().read_fn(path)
                backend_name = "pyarrow"
            else:
                try:
                    frame = _polars_backend().read_fn(path)
                    backend_name = "polars"
                except MissingParquetDependencyError as exc:
                    raise MissingParquetDependencyError(
                        "Unable to read parquet file without pyarrow or polars. Install 'geosync[feature_store]'."
                    ) from exc
            index_path = path.with_suffix(".index.json")
            if index_path.exists():
                index_frame = _json_backend().read_fn(index_path)
                for column in index_frame.columns:
                    try:
                        index_frame[column] = pd.to_datetime(index_frame[column])
                    except (
                        TypeError,
                        ValueError,
                    ):  # pragma: no cover - heterogeneous index
                        continue
                names_path = path.with_suffix(".index.names.json")
                index_names: list[str | None] | None = None
                if names_path.exists():
                    with names_path.open("r", encoding="utf-8") as handle:
                        raw_names = json.load(handle)
                    index_names = [name if name is not None else None for name in raw_names]
                if index_names and len(index_names) == index_frame.shape[1]:
                    index_frame.columns = index_names
                if index_frame.shape[1] == 1:
                    series = index_frame.iloc[:, 0]
                    frame.index = pd.Index(series, name=series.name)
                else:
                    frame.index = pd.MultiIndex.from_frame(
                        index_frame, names=list(index_frame.columns)
                    )
                if backend_name == "polars":
                    _drop_polars_index_columns(frame, index_frame)
            return frame
        if allow_json_fallback and suffix == _JSON_SUFFIX:
            return _json_backend().read_fn(path)
        raise ValueError(f"Unsupported dataframe suffix '{suffix}'")

    base = path
    parquet_path = base.with_suffix(_PARQUET_SUFFIX)
    if parquet_path.exists():
        return read_dataframe(parquet_path, allow_json_fallback=allow_json_fallback)
    json_path = base.with_suffix(_JSON_SUFFIX)
    if allow_json_fallback and json_path.exists():
        return _json_backend().read_fn(json_path)
    return pd.DataFrame()


def purge_dataframe_artifacts(base_path: Path) -> None:
    """Remove serialized dataframe artefacts for ``base_path``."""

    for suffix in (_PARQUET_SUFFIX, _JSON_SUFFIX):
        candidate = base_path.with_suffix(suffix)
        if candidate.exists():
            candidate.unlink()
    index_path = base_path.with_suffix(".index.json")
    if index_path.exists():
        index_path.unlink()
    names_path = base_path.with_suffix(".index.names.json")
    if names_path.exists():
        names_path.unlink()


def dataframe_to_parquet_bytes(frame: pd.DataFrame, *, index: bool = False) -> bytes:
    """Return a parquet-encoded payload for ``frame`` using the preferred backend."""

    backend = _select_backend(require_parquet=True, allow_json_fallback=False)
    if backend.to_bytes_fn is None:
        raise MissingParquetDependencyError(
            "The selected backend does not support parquet serialization to bytes."
        )
    return backend.to_bytes_fn(frame, index)
