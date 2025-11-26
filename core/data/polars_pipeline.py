"""Utilities for constructing zero-copy Polars pipelines."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from ..utils.logging import get_logger

try:  # pragma: no cover - optional dependency
    import polars as pl
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pl = None

try:  # pragma: no cover - optional dependency
    import pyarrow as pa
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pa = None

if TYPE_CHECKING:  # pragma: no cover - typing helpers
    from polars import DataFrame, LazyFrame
    from pyarrow import MemoryPool


_logger = get_logger(__name__)


class _Sentinel:
    pass


_UNSET = _Sentinel()


@dataclass(frozen=True)
class ParquetFileSummary:
    """Minimal summary of a parquet file for quick health checks."""

    path: str
    rows: int
    columns: list[str]
    compression: dict[str, str]
    size_bytes: int
    schema: str


def _require_polars() -> Any:
    if pl is None:  # pragma: no cover - safety net when polars absent
        raise RuntimeError(
            "polars is not installed. Install it with 'pip install polars' to use the "
            "lazy pipeline helpers."
        )
    return pl


def _infer_file_format(path: str | Path, explicit: str | None) -> str:
    if explicit is not None:
        return explicit.lower()
    resolved = Path(path)
    suffix = resolved.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return "parquet"
    if resolved.is_dir() and any(resolved.glob("**/*.parquet")):
        return "parquet"
    return "csv"


def _apply_predicates(
    lazy_frame: "LazyFrame", predicates: Any, module: Any
) -> "LazyFrame":
    if predicates in (None, _UNSET):
        return lazy_frame

    def _iter_predicates() -> list[Any]:
        if isinstance(predicates, Sequence) and not isinstance(
            predicates, (str, bytes)
        ):
            return list(predicates)
        return [predicates]

    for predicate in _iter_predicates():
        expr = predicate(module) if callable(predicate) else predicate
        lazy_frame = lazy_frame.filter(expr)
    return lazy_frame


def _resolve_partitioned_sources(
    root: str | Path,
    *,
    file_glob: str | None,
    suffix: str,
    partition_filters: Mapping[str, Sequence[str] | str] | None,
) -> str | list[str]:
    base_path = Path(root)
    if base_path.is_file():
        return str(base_path)

    if file_glob:
        return str(base_path / file_glob)

    if not partition_filters:
        return str(base_path)

    normalized_filters: dict[str, set[str]] = {}
    for key, values in partition_filters.items():
        if isinstance(values, (str, bytes)):
            normalized_filters[key] = {str(values)}
        else:
            normalized_filters[key] = {str(value) for value in values}

    candidates: list[str] = []
    for file in base_path.rglob(f"*{suffix}"):
        relative_parts = file.relative_to(base_path).parts[:-1]
        encountered_keys: set[str] = set()
        for part in relative_parts:
            if "=" not in part:
                continue
            column, value = part.split("=", 1)
            allowed = normalized_filters.get(column)
            if allowed is not None:
                encountered_keys.add(column)
                if value not in allowed:
                    break
        else:
            if normalized_filters.keys() <= encountered_keys:
                candidates.append(str(file))

    if not candidates:
        raise FileNotFoundError(
            f"No parquet files matched the partition filters at {base_path!s}"
        )
    return sorted(candidates)


def _normalize_polars_dtype(dtype: Any, module: Any) -> Any:
    try:
        return module.datatypes.py_type_to_dtype(dtype)
    except (TypeError, ValueError):
        pass

    if isinstance(dtype, np.dtype):
        return _normalize_polars_dtype(dtype.type, module)

    if isinstance(dtype, str):
        candidate = getattr(module, dtype, None)
        if candidate is not None:
            return candidate
    return dtype


def scan_lazy(
    path: str | Path,
    *,
    columns: Sequence[str] | None = None,
    predicate: Any = _UNSET,
    partition_filters: Mapping[str, Sequence[str] | str] | None = None,
    file_format: str | None = None,
    file_glob: str | None = None,
    memory_map: bool = True,
    low_memory: bool = True,
    row_count_name: str | None = None,
    cache: bool = False,
) -> "LazyFrame":
    """Create a lazy Polars scan with streaming-friendly defaults."""
    module = _require_polars()
    detected_format = _infer_file_format(path, file_format)
    if detected_format == "parquet":
        return scan_parquet_lazy(
            path,
            columns=columns,
            predicate=predicate,
            partition_filters=partition_filters,
            file_glob=file_glob,
            row_count_name=row_count_name,
            cache=cache,
        )

    _logger.debug(
        "Creating Polars lazy scan",
        path=str(path),
        columns=columns,
        memory_map=memory_map,
    )
    lazy_frame = module.scan_csv(
        path,
        columns=columns,
        low_memory=low_memory,
        memory_map=memory_map,
    )
    lazy_frame = _apply_predicates(lazy_frame, predicate, module)
    if row_count_name is not None:
        lazy_frame = lazy_frame.with_row_count(name=row_count_name)
    if cache:
        lazy_frame = lazy_frame.cache()
    return lazy_frame


def collect_streaming(
    lazy_frame: "LazyFrame",
    *,
    streaming: bool = True,
    sink: Callable[["DataFrame"], Any] | None = None,
) -> "DataFrame":
    """Collect a lazy frame with streaming enabled by default."""
    _require_polars()
    _logger.debug("Collecting Polars lazy frame", streaming=streaming)
    result = lazy_frame.collect(streaming=streaming)
    if sink is not None:
        sink(result)
    return result


def lazy_column_zero_copy(
    lazy_frame: "LazyFrame",
    column: str,
    *,
    streaming: bool = True,
) -> np.ndarray:
    """Extract a column as a zero-copy NumPy array."""
    module = _require_polars()
    if pa is None:  # pragma: no cover - optional dependency guard
        raise RuntimeError("pyarrow is required for zero-copy column extraction")
    _logger.debug("Extracting zero-copy column", column=column, streaming=streaming)
    arrow_table = (
        lazy_frame.select(module.col(column)).collect(streaming=streaming).to_arrow()
    )
    if arrow_table.num_columns != 1:
        raise ValueError("Expected a single-column selection for zero-copy extraction")
    return arrow_table.column(0).to_numpy(zero_copy_only=True)


@contextmanager
def use_arrow_memory_pool(pool: "MemoryPool"):
    """Temporarily route Arrow allocations through ``pool``."""
    if pa is None:  # pragma: no cover - optional dependency guard
        raise RuntimeError("pyarrow is required to manage the memory pool")
    try:
        previous_pool = pa.default_memory_pool()
        pa.set_memory_pool(pool)
    except AttributeError:  # pragma: no cover - pyarrow without setter
        _logger.warning("pyarrow does not support swapping the global memory pool")
        yield
    else:
        try:
            yield
        finally:
            pa.set_memory_pool(previous_pool)


def enable_global_string_cache(enable: bool = True) -> None:
    """Enable or disable the Polars global string cache."""
    module = _require_polars()
    module.Config.set_global_string_cache(enable)


def scan_parquet_lazy(
    path: str | Path,
    *,
    columns: Sequence[str] | None = None,
    predicate: Any = _UNSET,
    partition_filters: Mapping[str, Sequence[str] | str] | None = None,
    file_glob: str | None = None,
    row_count_name: str | None = None,
    cache: bool = False,
    use_statistics: bool = True,
    allow_predicate_pushdown: bool = True,
    allow_projection_pushdown: bool = True,
    low_memory: bool = False,
    rechunk: bool = False,
) -> "LazyFrame":
    """Create a lazy Parquet scan with partition pruning and pushdown enabled."""

    module = _require_polars()
    sources = _resolve_partitioned_sources(
        path,
        file_glob=file_glob,
        suffix=".parquet",
        partition_filters=partition_filters,
    )
    _logger.debug(
        "Creating Polars lazy parquet scan",
        path=str(path),
        sources=sources,
        columns=columns,
        partition_filters=partition_filters,
    )
    lazy_frame = module.scan_parquet(
        sources,
        columns=columns,
        cache=cache,
        use_statistics=use_statistics,
        allow_predicate_pushdown=allow_predicate_pushdown,
        allow_projection_pushdown=allow_projection_pushdown,
        low_memory=low_memory,
        rechunk=rechunk,
    )
    lazy_frame = _apply_predicates(lazy_frame, predicate, module)
    if row_count_name is not None:
        lazy_frame = lazy_frame.with_row_count(name=row_count_name)
    return lazy_frame


def cache_lazy_frame(lazy_frame: "LazyFrame") -> "LazyFrame":
    """Cache the lazy frame to re-use intermediate results across branches."""

    _require_polars()
    _logger.debug("Caching lazy frame")
    return lazy_frame.cache()


def apply_vectorized(
    lazy_frame: "LazyFrame",
    *,
    expressions: Mapping[str, Callable[[Any], Any] | Any],
) -> "LazyFrame":
    """Apply vectorised transformations ensuring columns remain lazily evaluated."""

    module = _require_polars()
    resolved_expressions: list[Any] = []
    for alias, expr in expressions.items():
        candidate = expr(module) if callable(expr) else expr
        if hasattr(candidate, "alias"):
            candidate = candidate.alias(alias)
        resolved_expressions.append(candidate)
    _logger.debug("Applying vectorized expressions", aliases=list(expressions.keys()))
    return lazy_frame.with_columns(resolved_expressions)


def enforce_schema(
    lazy_frame: "LazyFrame",
    schema: Mapping[str, Any],
    *,
    strict: bool = True,
) -> "LazyFrame":
    """Ensure columns conform to the provided Polars schema."""

    module = _require_polars()
    casts: list[Any] = []
    for column, dtype in schema.items():
        normalized_dtype = _normalize_polars_dtype(dtype, module)
        casts.append(module.col(column).cast(normalized_dtype, strict=strict))
    _logger.debug("Enforcing schema", columns=list(schema.keys()))
    return lazy_frame.with_columns(casts)


def profile_lazy_frame(lazy_frame: "LazyFrame") -> dict[str, Any]:
    """Return planning artefacts for profiling and hot-path inspection."""

    _require_polars()
    plan = lazy_frame.describe_plan()
    optimized_plan = lazy_frame.describe_optimized_plan()
    profile = lazy_frame.profile()
    return {
        "plan": plan,
        "optimized_plan": optimized_plan,
        "profile": profile,
    }


def summarize_parquet_dataset(
    path: str | Path,
    *,
    limit_files: int | None = None,
) -> list[ParquetFileSummary]:
    """Inspect parquet files for schema, compression and size diagnostics."""

    if pa is None:  # pragma: no cover - optional dependency guard
        raise RuntimeError("pyarrow is required to inspect parquet metadata")

    base = Path(path)
    paths: list[Path]
    if base.is_file():
        paths = [base]
    else:
        paths = sorted(base.rglob("*.parquet"))
    if limit_files is not None:
        paths = paths[:limit_files]

    summaries: list[ParquetFileSummary] = []
    for file_path in paths:
        parquet_file = pa.parquet.ParquetFile(file_path)
        metadata = parquet_file.metadata
        column_names = [
            metadata.schema.column(i).name for i in range(metadata.num_columns)
        ]
        compression: dict[str, str] = {}
        if metadata.num_row_groups:
            row_group = metadata.row_group(0)
            for idx, name in enumerate(column_names):
                column_chunk = row_group.column(idx)
                compression[name] = getattr(column_chunk, "compression", "UNKNOWN")
        summaries.append(
            ParquetFileSummary(
                path=str(file_path),
                rows=metadata.num_rows,
                columns=column_names,
                compression=compression,
                size_bytes=file_path.stat().st_size,
                schema=str(parquet_file.schema_arrow),
            )
        )
    return summaries
