"""Tests for the shared L2 CLI helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from research.microstructure.l2_cli import (
    LoadedSubstrate,
    SubstrateError,
    add_common_args,
    load_substrate,
    parse_symbols,
    setup_logging,
)


def test_parse_symbols_canonical() -> None:
    assert parse_symbols("BTCUSDT,ETHUSDT,SOLUSDT") == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    )


def test_parse_symbols_strips_whitespace_and_uppercases() -> None:
    assert parse_symbols(" btcusdt ,  ethusdt ") == ("BTCUSDT", "ETHUSDT")


def test_parse_symbols_drops_empty_tokens() -> None:
    assert parse_symbols("BTCUSDT,,,ETHUSDT,") == ("BTCUSDT", "ETHUSDT")


def test_add_common_args_attaches_all_four(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser()
    add_common_args(parser, output_default=tmp_path / "out.json")
    # --help text must mention every standard flag
    args = parser.parse_args([])
    assert args.data_dir == Path("data/binance_l2_perp")
    assert args.symbols.startswith("BTCUSDT")
    assert args.output == tmp_path / "out.json"
    assert args.log_level == "INFO"


def test_add_common_args_accepts_overrides(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser()
    add_common_args(parser, output_default=tmp_path / "out.json")
    args = parser.parse_args(
        [
            "--data-dir",
            "/tmp/x",
            "--symbols",
            "A,B,C",
            "--output",
            "/tmp/y.json",
            "--log-level",
            "DEBUG",
        ]
    )
    assert args.data_dir == Path("/tmp/x")
    assert args.symbols == "A,B,C"
    assert args.output == Path("/tmp/y.json")
    assert args.log_level == "DEBUG"


def test_setup_logging_accepts_string_level() -> None:
    setup_logging("WARNING")
    setup_logging("INFO")
    setup_logging("DEBUG")


def test_load_substrate_missing_dir_raises() -> None:
    with pytest.raises(SubstrateError, match="does not exist"):
        load_substrate(Path("/definitely/does/not/exist"), "BTCUSDT")


def test_load_substrate_empty_dir_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SubstrateError, match="no parquet"):
        load_substrate(empty, "BTCUSDT")


def test_load_substrate_returns_loaded_on_real_substrate() -> None:
    """Smoke-check the happy path using the committed Session 1 substrate."""
    data_dir = Path("data/binance_l2_perp")
    if not data_dir.exists():
        pytest.skip("Session 1 substrate not available")
    loaded = load_substrate(data_dir, "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT")
    assert isinstance(loaded, LoadedSubstrate)
    assert loaded.features.n_symbols == 5
    assert loaded.features.n_rows > 1000


def test_help_text_includes_every_flag(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser(prog="probe")
    add_common_args(parser, output_default=tmp_path / "out.json")
    help_text = parser.format_help()
    for flag in ("--data-dir", "--symbols", "--output", "--log-level"):
        assert flag in help_text


def test_headline_metrics_json_still_consumable_after_refactor() -> None:
    """Sanity: the shared module does not break existing artifact contracts."""
    path = Path("results/L2_HEADLINE_METRICS.json")
    if not path.exists():
        pytest.skip("headline metrics not present")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert "ic_pooled" in data
