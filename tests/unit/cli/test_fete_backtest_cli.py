"""Tests for the `fete-backtest` CLI command."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from click.testing import CliRunner

from cli.tradepulse_cli import cli


def _write_sample_csv(path: Path) -> None:
    frame = pd.DataFrame(
        {
            "price": [100.0, 101.5, 100.2, 102.8, 103.1],
            "prob": [0.55, 0.47, 0.51, 0.6, 0.58],
        }
    )
    frame.to_csv(path, index=False)


def test_fete_backtest_cli_produces_equity_curve(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    out_path = tmp_path / "equity.csv"
    _write_sample_csv(csv_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "fete-backtest",
            "--csv",
            str(csv_path),
            "--prob-col",
            "prob",
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "FETE Backtest" in result.output
    assert "Final Equity" in result.output
    assert "Trades" in result.output
    assert out_path.exists()
    equity = pd.read_csv(out_path)
    assert list(equity.columns) == ["timestamp", "equity"]
    assert len(equity) == 5
