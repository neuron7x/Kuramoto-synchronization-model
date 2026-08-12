# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import importlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

polars_pipeline = importlib.import_module("core.data.polars_pipeline")


class DummyArrowColumn:
    def __init__(self, array: np.ndarray):
        self._array = array

    def to_numpy(
        self, zero_copy_only: bool = True
    ) -> np.ndarray:  # pragma: no cover - pass through
        return self._array


class DummyArrowTable:
    def __init__(self, data: dict[str, np.ndarray]):
        self._data = data

    @property
    def num_columns(self) -> int:
        return len(self._data)

    def column(self, index: int) -> DummyArrowColumn:
        key = list(self._data.keys())[index]
        return DummyArrowColumn(self._data[key])


class DummyDataFrame:
    def __init__(self, data: dict[str, np.ndarray]):
        self._data = data

    def to_arrow(self) -> DummyArrowTable:
        return DummyArrowTable(self._data)


@dataclass
class AliasExpression:
    name: str
    alias: str


@dataclass
class CastExpression:
    name: str
    dtype: object
    strict: bool


class StubExpression:
    def __init__(self, name: str):
        self.name = name
        self.alias_calls: list[str] = []
        self.cast_calls: list[tuple[object, bool]] = []

    def alias(self, alias: str) -> AliasExpression:
        self.alias_calls.append(alias)
        return AliasExpression(self.name, alias)

    def cast(self, dtype: object, strict: bool = True) -> CastExpression:
        self.cast_calls.append((dtype, strict))
        return CastExpression(self.name, dtype, strict)


class DummyLazyFrame:
    def __init__(self, data: dict[str, np.ndarray]):
        self._data = data
        self.collected = 0
        self.row_count_name: str | None = None
        self.filters: list[object] = []
        self.cached = False
        self.columns_added: list[object] = []
        self.plan = "PLAN"
        self.optimized_plan = "OPTIMIZED"

    def with_row_count(self, name: str) -> "DummyLazyFrame":
        self.row_count_name = name
        return self

    def collect(self, streaming: bool = True) -> DummyDataFrame:
        self.collected += 1
        return DummyDataFrame(self._data)

    def select(self, column_expr: object) -> "DummyLazyFrame":
        if hasattr(column_expr, "name"):
            column_name = column_expr.name  # type: ignore[attr-defined]
        else:
            column_name = column_expr  # type: ignore[assignment]
        return DummyLazyFrame({column_name: self._data[column_name]})

    def filter(self, expr: object) -> "DummyLazyFrame":
        self.filters.append(expr)
        return self

    def cache(self) -> "DummyLazyFrame":
        self.cached = True
        return self

    def with_columns(self, expressions: list[object]) -> "DummyLazyFrame":
        self.columns_added.extend(expressions)
        return self

    def describe_plan(self) -> str:
        return self.plan

    def describe_optimized_plan(self) -> str:
        return self.optimized_plan

    def profile(self) -> dict[str, object]:
        return {"rows": next(iter(self._data.values())).size, "plan": self.plan}


class StubPolars:
    class Config:
        cache_enabled = False

        @classmethod
        def set_global_string_cache(cls, enable: bool) -> None:
            cls.cache_enabled = enable

    class datatypes:
        @staticmethod
        def py_type_to_dtype(dtype: object) -> object:
            return dtype

    def __init__(self, lazy_frame: DummyLazyFrame):
        self.lazy_frame = lazy_frame
        self.scan_csv_calls: list[tuple] = []
        self.scan_parquet_calls: list[tuple] = []

    def scan_csv(self, *args, **kwargs) -> DummyLazyFrame:
        self.scan_csv_calls.append((args, kwargs))
        return self.lazy_frame

    def scan_parquet(self, source: object, **kwargs: object) -> DummyLazyFrame:
        self.scan_parquet_calls.append((source, kwargs))
        return self.lazy_frame

    @staticmethod
    def col(name: str) -> StubExpression:
        return StubExpression(name)


class StubArrowModule:
    def __init__(self) -> None:
        self._pool = object()
        self.calls: list[object] = []

    def default_memory_pool(self) -> object:
        return self._pool

    def set_memory_pool(self, pool: object) -> None:
        self.calls.append(pool)
        self._pool = pool


@pytest.fixture(autouse=True)
def restore_modules(monkeypatch):
    # ensure module globals reset after each test
    monkeypatch.setattr(polars_pipeline, "pl", None)
    monkeypatch.setattr(polars_pipeline, "pa", None)
    yield


def test_scan_lazy_requires_polars(monkeypatch):
    with pytest.raises(RuntimeError, match="polars is not installed"):
        polars_pipeline.scan_lazy("/tmp/example.csv")


def test_scan_lazy_uses_stub_polars(monkeypatch):
    data = {"price": np.array([1.0, 2.0, 3.0])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    lazy_frame = polars_pipeline.scan_lazy("/tmp/example.csv", row_count_name="row_id")

    assert lazy_frame is stub_lazy
    assert stub_lazy.row_count_name == "row_id"
    assert stub_pl.scan_csv_calls[0][1]["columns"] is None


def test_scan_lazy_detects_parquet_and_routes_to_parquet_scan(tmp_path, monkeypatch):
    (tmp_path / "date=2024-01-01" / "symbol=AAPL").mkdir(parents=True)
    parquet_path = tmp_path / "date=2024-01-01" / "symbol=AAPL" / "data.parquet"
    parquet_path.write_bytes(b"")

    data = {"price": np.array([1.0, 2.0, 3.0])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    lazy_frame = polars_pipeline.scan_lazy(
        tmp_path,
        columns=["price"],
        predicate=lambda pl_mod: ("predicate", pl_mod),
        partition_filters={"symbol": ["AAPL"]},
        row_count_name="row_id",
    )

    assert lazy_frame is stub_lazy
    assert stub_pl.scan_parquet_calls
    source, kwargs = stub_pl.scan_parquet_calls[0]
    assert parquet_path.as_posix() in source
    assert kwargs["columns"] == ["price"]
    assert stub_lazy.filters == [("predicate", stub_pl)]
    assert stub_lazy.row_count_name == "row_id"


def test_resolve_partitioned_sources_skips_files_missing_keys(tmp_path):
    partitioned_dir = tmp_path / "symbol=AAPL"
    partitioned_dir.mkdir()
    partitioned_file = partitioned_dir / "data.parquet"
    partitioned_file.write_bytes(b"")

    non_partitioned_file = tmp_path / "fallback.parquet"
    non_partitioned_file.write_bytes(b"")

    sources = polars_pipeline._resolve_partitioned_sources(
        tmp_path,
        file_glob=None,
        suffix=".parquet",
        partition_filters={"symbol": ["AAPL"]},
    )

    assert sources == [partitioned_file.as_posix()]


def test_collect_streaming_invokes_sink(monkeypatch):
    data = {"volume": np.array([10, 20])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    sink_calls: list[DummyDataFrame] = []

    result = polars_pipeline.collect_streaming(stub_lazy, sink=sink_calls.append)

    assert isinstance(result, DummyDataFrame)
    assert sink_calls == [result]
    assert stub_lazy.collected == 1


def test_lazy_column_zero_copy_returns_numpy_view(monkeypatch):
    data = {"returns": np.array([0.1, 0.2, 0.3])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    stub_pa = StubArrowModule()
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)
    monkeypatch.setattr(polars_pipeline, "pa", stub_pa)

    array = polars_pipeline.lazy_column_zero_copy(stub_lazy, "returns")

    assert array is data["returns"]


def test_lazy_column_zero_copy_requires_arrow(monkeypatch):
    data = {"returns": np.array([0.1, 0.2, 0.3])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    with pytest.raises(RuntimeError, match="pyarrow is required"):
        polars_pipeline.lazy_column_zero_copy(stub_lazy, "returns")


def test_use_arrow_memory_pool_temporarily_swaps_pool(monkeypatch):
    data = {"returns": np.array([0.1, 0.2])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)
    stub_pa = StubArrowModule()
    previous_pool = stub_pa.default_memory_pool()
    replacement = object()
    monkeypatch.setattr(polars_pipeline, "pa", stub_pa)

    with polars_pipeline.use_arrow_memory_pool(replacement):
        assert stub_pa._pool is replacement

    assert stub_pa._pool is previous_pool
    assert stub_pa.calls == [replacement, previous_pool]


def test_enable_global_string_cache_delegates(monkeypatch):
    stub_lazy = DummyLazyFrame({"price": np.array([1.0])})
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    polars_pipeline.enable_global_string_cache(True)

    assert stub_pl.Config.cache_enabled is True


def test_cache_lazy_frame_marks_lazy_frame_cached(monkeypatch):
    data = {"price": np.array([1.0])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    cached = polars_pipeline.cache_lazy_frame(stub_lazy)

    assert cached is stub_lazy
    assert stub_lazy.cached is True


def test_apply_vectorized_uses_alias(monkeypatch):
    data = {"price": np.array([1.0])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    result = polars_pipeline.apply_vectorized(
        stub_lazy,
        expressions={"returns": lambda pl_mod: pl_mod.col("price")},
    )

    assert result is stub_lazy
    assert isinstance(stub_lazy.columns_added[0], AliasExpression)
    assert stub_lazy.columns_added[0].alias == "returns"


def test_enforce_schema_casts_columns(monkeypatch):
    data = {"price": np.array([1.0])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    polars_pipeline.enforce_schema(stub_lazy, {"price": float})

    cast_expr = stub_lazy.columns_added[0]
    assert isinstance(cast_expr, CastExpression)
    assert cast_expr.name == "price"


def test_profile_lazy_frame_exposes_plans(monkeypatch):
    data = {"price": np.array([1.0, 2.0])}
    stub_lazy = DummyLazyFrame(data)
    stub_pl = StubPolars(stub_lazy)
    monkeypatch.setattr(polars_pipeline, "pl", stub_pl)

    profile = polars_pipeline.profile_lazy_frame(stub_lazy)

    assert profile["plan"] == "PLAN"
    assert profile["optimized_plan"] == "OPTIMIZED"
    assert profile["profile"]["rows"] == 2


class StubParquetColumn:
    def __init__(self, compression: str):
        self.compression = compression


class StubRowGroup:
    def __init__(self, compressions: list[str]):
        self._compressions = compressions

    def column(self, index: int) -> StubParquetColumn:
        return StubParquetColumn(self._compressions[index])


class StubSchemaColumn:
    def __init__(self, name: str):
        self.name = name


class StubSchema:
    def __init__(self, columns: list[str]):
        self._columns = columns

    def column(self, index: int) -> StubSchemaColumn:
        return StubSchemaColumn(self._columns[index])


class StubMetadata:
    def __init__(self, rows: int, column_names: list[str], compressions: list[str]):
        self.num_rows = rows
        self.num_columns = len(column_names)
        self.num_row_groups = 1
        self.schema = StubSchema(column_names)
        self._row_group = StubRowGroup(compressions)

    def row_group(self, index: int) -> StubRowGroup:
        assert index == 0
        return self._row_group


class StubParquetFile:
    def __init__(self, rows: int, column_names: list[str], compressions: list[str]):
        self.metadata = StubMetadata(rows, column_names, compressions)
        self.schema_arrow = "schema"


class StubPyArrow(StubArrowModule):
    def __init__(self, parquet_file: StubParquetFile):
        super().__init__()
        self._parquet_file = parquet_file
        self.parquet = self

    # pyarrow.parquet.ParquetFile shim
    def ParquetFile(self, path: Path) -> StubParquetFile:  # type: ignore[override]
        return self._parquet_file


def test_summarize_parquet_dataset_requires_pyarrow(monkeypatch, tmp_path):
    monkeypatch.setattr(polars_pipeline, "pa", None)

    with pytest.raises(RuntimeError, match="pyarrow is required"):
        polars_pipeline.summarize_parquet_dataset(tmp_path)


def test_summarize_parquet_dataset_returns_summary(monkeypatch, tmp_path):
    parquet_path = tmp_path / "example.parquet"
    parquet_path.write_bytes(b"12345")

    stub_file = StubParquetFile(100, ["price", "volume"], ["zstd", "lz4"])
    stub_pa = StubPyArrow(stub_file)
    monkeypatch.setattr(polars_pipeline, "pa", stub_pa)

    summaries = polars_pipeline.summarize_parquet_dataset(parquet_path)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.path == parquet_path.as_posix()
    assert summary.rows == 100
    assert summary.columns == ["price", "volume"]
    assert summary.compression["price"] == "zstd"
    assert summary.size_bytes == parquet_path.stat().st_size
