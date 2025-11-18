from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import pytest

from core.utils import dataframe_io


@pytest.fixture(autouse=True)
def _reset_backends():
    """Ensure backend discovery caches do not leak between tests."""

    dataframe_io.reset_dataframe_io_backends()
    yield
    dataframe_io.reset_dataframe_io_backends()


def test_pyarrow_detection_handles_missing_dependency(monkeypatch):
    """``_pyarrow_available`` should gracefully handle missing dependencies."""

    call_log: list[str] = []

    def fake_import(name: str):
        call_log.append(name)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    assert dataframe_io._pyarrow_available() is False
    assert call_log == ["pyarrow"]


def test_polars_backend_prepares_index_and_roundtrips(tmp_path, monkeypatch):
    """The polars backend should reset the index and support roundtrips."""

    storage: dict[str, pd.DataFrame] = {}

    class _Dataset:
        def __init__(self, frame: pd.DataFrame) -> None:
            self._frame = frame.copy()

        def write_parquet(self, buffer):
            storage["written"] = self._frame.copy()
            buffer.write(b"parquet")

        def to_pandas(self, *, use_pyarrow: bool = False):
            return self._frame.copy()

        def to_dict(self, *, as_series: bool = False):
            assert as_series is False
            return {column: self._frame[column].tolist() for column in self._frame.columns}

    class _PolarsModule:
        def from_pandas(self, frame: pd.DataFrame) -> _Dataset:
            storage["from_pandas"] = frame.copy()
            return _Dataset(frame)

        def DataFrame(self, data, *, strict: bool = False):  # pragma: no cover - signature parity
            frame = pd.DataFrame(data)
            return _Dataset(frame)

        def read_parquet(self, path: Path) -> _Dataset:  # pragma: no cover - signature parity
            return _Dataset(storage["written"])

    monkeypatch.setattr(dataframe_io, "_load_polars", lambda: _PolarsModule())

    backend = dataframe_io._polars_backend()

    original = pd.DataFrame({"alpha": [1.0, 2.0]})
    path = tmp_path / "data.parquet"

    backend.write_fn(original, path, index=True)
    assert path.exists()
    pd.testing.assert_frame_equal(storage["from_pandas"], original.reset_index())

    round_trip = backend.read_fn(path)
    pd.testing.assert_frame_equal(round_trip, storage["written"])

    payload = backend.to_bytes_fn(original, index=False)
    assert payload == b"parquet"


def test_polars_backend_read_falls_back_without_pyarrow(tmp_path, monkeypatch):
    """Reading via polars should not require pyarrow to be installed."""

    storage: dict[str, pd.DataFrame] = {}

    class _Dataset:
        def __init__(self, frame: pd.DataFrame) -> None:
            self._frame = frame.copy()

        def write_parquet(self, buffer):
            storage["written"] = self._frame.copy()
            buffer.write(b"parquet")

        def to_pandas(self, *, use_pyarrow: bool = False):
            raise ModuleNotFoundError("No module named 'pyarrow'", name="pyarrow")

        def to_dict(self, *, as_series: bool = False):
            assert as_series is False
            return {column: self._frame[column].tolist() for column in self._frame.columns}

    class _PolarsModule:
        def __init__(self) -> None:
            self.created_from_dict: dict[str, list] | None = None

        def from_pandas(self, frame: pd.DataFrame) -> _Dataset:
            storage["from_pandas"] = frame.copy()
            return _Dataset(frame)

        def DataFrame(self, data, *, strict: bool = False):  # pragma: no cover - signature parity
            self.created_from_dict = data
            frame = pd.DataFrame(data)
            return _Dataset(frame)

        def read_parquet(self, path: Path) -> _Dataset:  # pragma: no cover - signature parity
            return _Dataset(storage["written"])

    monkeypatch.setattr(dataframe_io, "_load_polars", lambda: _PolarsModule())

    backend = dataframe_io._polars_backend()

    original = pd.DataFrame({"alpha": [1.0, 2.0], "beta": pd.date_range("2023-01-01", periods=2)})
    path = tmp_path / "data.parquet"

    backend.write_fn(original, path, index=False)
    assert path.exists()

    round_trip = backend.read_fn(path)
    pd.testing.assert_frame_equal(round_trip, original.reset_index(drop=True))


def test_polars_backend_prepare_falls_back_without_pyarrow(tmp_path, monkeypatch):
    """``_prepare`` should materialize via dictionaries when pyarrow is absent."""

    storage: dict[str, pd.DataFrame] = {}

    class _Dataset:
        def __init__(self, frame: pd.DataFrame) -> None:
            self._frame = frame.copy()

        def write_parquet(self, buffer):
            storage["written"] = self._frame.copy()
            buffer.write(b"parquet")

        def to_pandas(self, *, use_pyarrow: bool = False):  # pragma: no cover - unused in test
            return self._frame.copy()

        def to_dict(self, *, as_series: bool = False):  # pragma: no cover - unused in test
            assert as_series is False
            return {column: self._frame[column].tolist() for column in self._frame.columns}

    class _PolarsModule:
        def __init__(self) -> None:
            self.created_from_dict: dict[str, list] | None = None

        def from_pandas(self, frame: pd.DataFrame) -> _Dataset:
            raise ImportError("pyarrow missing")

        def DataFrame(self, data, *, strict: bool = False):
            self.created_from_dict = data
            frame = pd.DataFrame(data)
            return _Dataset(frame)

        def read_parquet(self, path: Path) -> _Dataset:  # pragma: no cover - signature parity
            return _Dataset(storage["written"])

    module = _PolarsModule()
    monkeypatch.setattr(dataframe_io, "_load_polars", lambda: module)

    backend = dataframe_io._polars_backend()

    original = pd.DataFrame({"value": [1.0, 2.5]}, index=pd.Index(["row1", "row2"], name="id"))
    path = tmp_path / "data.parquet"

    backend.write_fn(original, path, index=True)
    assert path.exists()

    expected_payload = original.reset_index().to_dict(orient="list")
    assert module.created_from_dict == expected_payload


def test_select_backend_prefers_json_when_allowed(monkeypatch):
    json_backend = dataframe_io._json_backend()

    monkeypatch.setattr(dataframe_io, "_available_backends", lambda: [json_backend])

    selected = dataframe_io._select_backend(require_parquet=False, allow_json_fallback=True)
    assert selected.name == "json"


def test_select_backend_requires_parquet(monkeypatch):
    monkeypatch.setattr(dataframe_io, "_available_backends", lambda: [dataframe_io._json_backend()])

    with pytest.raises(dataframe_io.MissingParquetDependencyError):
        dataframe_io._select_backend(require_parquet=True, allow_json_fallback=False)


def test_write_dataframe_uses_json_extension(monkeypatch, tmp_path):
    backend = dataframe_io._json_backend()

    monkeypatch.setattr(dataframe_io, "_available_backends", lambda: [backend])

    frame = pd.DataFrame({"x": [1, 2]})
    destination = tmp_path / "dataset"

    written = dataframe_io.write_dataframe(frame, destination, allow_json_fallback=True)
    assert written.suffix == ".json"
    assert written.read_text()


def test_write_dataframe_requires_parquet_suffix(monkeypatch, tmp_path):
    backend = dataframe_io._json_backend()

    monkeypatch.setattr(dataframe_io, "_available_backends", lambda: [backend])

    frame = pd.DataFrame({"y": [3, 4]})
    destination = tmp_path / "data.parquet"

    with pytest.raises(dataframe_io.MissingParquetDependencyError):
        dataframe_io.write_dataframe(frame, destination)


def test_read_dataframe_resolves_base_path(tmp_path, monkeypatch):
    frame = pd.DataFrame({"z": [5]})
    backend = dataframe_io._json_backend()

    monkeypatch.setattr(dataframe_io, "_available_backends", lambda: [backend])

    target = tmp_path / "feature"
    dataframe_io.write_dataframe(frame, target, allow_json_fallback=True)

    loaded = dataframe_io.read_dataframe(target, allow_json_fallback=True)
    pd.testing.assert_frame_equal(loaded, frame)


def test_read_dataframe_rejects_unknown_suffix(tmp_path):
    path = tmp_path / "payload.csv"
    path.write_text("irrelevant")

    with pytest.raises(ValueError):
        dataframe_io.read_dataframe(path)


def test_read_dataframe_requires_backend(monkeypatch, tmp_path):
    path = tmp_path / "payload.parquet"
    path.write_bytes(b"binary")

    monkeypatch.setattr(dataframe_io, "_pyarrow_available", lambda: False)

    def _raise_polars_backend():
        raise dataframe_io.MissingParquetDependencyError("no polars")

    monkeypatch.setattr(dataframe_io, "_polars_backend", _raise_polars_backend)

    with pytest.raises(dataframe_io.MissingParquetDependencyError):
        dataframe_io.read_dataframe(path)


def test_purge_dataframe_artifacts_removes_all(tmp_path):
    base = tmp_path / "artifact"
    parquet = base.with_suffix(".parquet")
    json_path = base.with_suffix(".json")
    parquet.write_bytes(b"data")
    json_path.write_text("{}")

    dataframe_io.purge_dataframe_artifacts(base)

    assert not parquet.exists()
    assert not json_path.exists()


def test_dataframe_to_parquet_bytes_requires_support(monkeypatch):
    backend = dataframe_io._json_backend()
    monkeypatch.setattr(dataframe_io, "_select_backend", lambda *a, **k: backend)

    with pytest.raises(dataframe_io.MissingParquetDependencyError):
        dataframe_io.dataframe_to_parquet_bytes(pd.DataFrame({}))
