"""Parquet compatibility helpers with deterministic diagnostics."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

import pandas as pd

ParquetEngine = Literal["auto", "pyarrow", "fastparquet"]


class ParquetEngineUnavailable(RuntimeError):
    """Raised when no parquet backend is available in the runtime."""


@lru_cache(maxsize=1)
def available_engines() -> tuple[str, ...]:
    engines: list[str] = []
    if importlib.util.find_spec("pyarrow") is not None:
        engines.append("pyarrow")
    if importlib.util.find_spec("fastparquet") is not None:
        engines.append("fastparquet")
    return tuple(engines)


def read_parquet_compat(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    engines = available_engines()
    if not engines:
        raise ParquetEngineUnavailable(
            "No parquet engine installed. Install 'pyarrow' or 'fastparquet'."
        )

    last_err: Exception | None = None
    for engine in engines:
        try:
            return pd.read_parquet(path, engine=cast(ParquetEngine, engine))
        except Exception as exc:  # pragma: no cover - backend-specific
            last_err = exc

    raise RuntimeError(f"Parquet read failed for all engines {engines}: {last_err}")
