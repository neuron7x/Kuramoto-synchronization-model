"""End-to-end regression covering ingest → features → signal → report."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from cli.tradepulse_cli import _load_prices, _resolve_strategy, _run_backtest, _write_frame
from core.config.cli_models import (
    BacktestConfig,
    DataSourceConfig,
    ExecConfig,
    ExecutionConfig,
    IngestConfig,
    ReportConfig,
    StrategyConfig,
)
from core.reporting import generate_markdown_report, render_markdown_to_html, render_markdown_to_pdf
from tests.tolerances import FLOAT_ABS_TOL


@pytest.mark.slow
def test_pipeline_from_scratch(tmp_path) -> None:
    """Validate the complete analytics pipeline on synthetic data."""
    timestamps = pd.date_range("2024-01-01", periods=240, freq="1min")
    rng = np.random.default_rng(1234)
    prices = 100 + rng.normal(0, 0.5, size=len(timestamps)).cumsum()
    volumes = rng.uniform(100, 1000, size=len(timestamps))
    raw_df = pd.DataFrame({"timestamp": timestamps, "price": prices, "volume": volumes})

    raw_path = tmp_path / "raw.csv"
    raw_df.to_csv(raw_path, index=False)

    artifacts_dir = tmp_path / "artifacts"
    ingest_cfg = IngestConfig(
        name="qa-ingest",
        source=DataSourceConfig(
            kind="csv", path=raw_path, timestamp_field="timestamp", value_field="price"
        ),
        destination=artifacts_dir / "ingested.csv",
    )

    ingested_frame = _load_prices(ingest_cfg)
    _write_frame(ingested_frame, ingest_cfg.destination)
    assert ingest_cfg.destination.exists()

    features = ingested_frame.copy()
    features["sma_fast"] = features["price"].rolling(window=5, min_periods=1).mean()
    features["sma_slow"] = features["price"].rolling(window=20, min_periods=1).mean()
    features_path = artifacts_dir / "features.csv"
    features_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(features_path, index=False)
    assert features_path.exists()

    backtest_cfg = BacktestConfig(
        name="qa-backtest",
        data=DataSourceConfig(
            kind="csv",
            path=features_path,
            timestamp_field="timestamp",
            value_field="price",
        ),
        strategy=StrategyConfig(
            entrypoint="core.strategies.signals:moving_average_signal",
            parameters={"window": 10},
        ),
        execution=ExecutionConfig(starting_cash=50_000.0),
        results_path=artifacts_dir / "backtest.json",
    )
    backtest_result = _run_backtest(backtest_cfg)
    backtest_cfg.results_path.write_text(
        json.dumps(backtest_result, indent=2, sort_keys=True), encoding="utf-8"
    )
    assert backtest_result["stats"]["trades"] >= 0
    assert backtest_cfg.results_path.exists()

    exec_cfg = ExecConfig(
        name="qa-exec",
        data=DataSourceConfig(
            kind="csv",
            path=features_path,
            timestamp_field="timestamp",
            value_field="price",
        ),
        strategy=backtest_cfg.strategy,
        results_path=artifacts_dir / "signal.json",
    )
    exec_frame = _load_prices(exec_cfg)
    prices_array = exec_frame[exec_cfg.data.value_field].to_numpy(dtype=float)
    strategy_fn = _resolve_strategy(exec_cfg.strategy)
    signals = strategy_fn(prices_array)
    latest_signal = float(signals[-1])
    exec_payload = {"latest_signal": latest_signal, "count": int(signals.size)}
    exec_cfg.results_path.write_text(
        json.dumps(exec_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    assert abs(latest_signal) <= 1.0 + FLOAT_ABS_TOL
    assert exec_cfg.results_path.exists()

    report_cfg = ReportConfig(
        name="qa-report",
        inputs=[backtest_cfg.results_path, exec_cfg.results_path],
        output_path=artifacts_dir / "report.md",
        html_output_path=artifacts_dir / "report.html",
        pdf_output_path=artifacts_dir / "report.pdf",
    )

    markdown_report = generate_markdown_report(report_cfg)
    report_cfg.output_path.write_text(markdown_report, encoding="utf-8")
    render_markdown_to_html(markdown_report, report_cfg.html_output_path)
    render_markdown_to_pdf(markdown_report, report_cfg.pdf_output_path)

    assert len(signals) == len(prices_array)
    assert "### Backtest" in markdown_report
    assert report_cfg.html_output_path.read_text(encoding="utf-8").startswith(
        "<!doctype html>"
    )
    pdf_bytes = report_cfg.pdf_output_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")
