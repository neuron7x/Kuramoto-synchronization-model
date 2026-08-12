from __future__ import annotations

from pathlib import Path

import pytest

from core.io.parquet_compat import ParquetEngineUnavailable, read_parquet_compat


def test_read_parquet_compat_raises_without_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    path = tmp_path / "sample.parquet"
    path.write_bytes(b"not-a-real-parquet")
    with pytest.raises(ParquetEngineUnavailable):
        read_parquet_compat(path)


def test_read_parquet_compat_raises_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    with pytest.raises(FileNotFoundError):
        read_parquet_compat(Path("does_not_exist.parquet"))
