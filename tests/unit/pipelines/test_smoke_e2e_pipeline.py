from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backtest.engine import Result
from core.data.ingestion import Ticker
from core.data.models import InstrumentType
from core.pipelines.smoke_e2e import (
    SmokeE2EConfig,
    SmokeE2EPipeline,
    write_summary,
)


def _make_tick(price: float) -> Ticker:
    return Ticker.create(
        symbol="TEST",
        venue="CSV",
        price=price,
        timestamp=0,
        volume=1,
        instrument_type=InstrumentType.SPOT,
    )


def test_pipeline_executes_all_stages(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("ts,price,volume\n0,100,1\n", encoding="utf-8")

    calls: dict[str, object] = {}

    def fake_analyzer(path: Path, seed: int) -> dict[str, float]:
        assert path == csv_path
        assert seed == 7
        calls["analyzer"] = True
        return {"delta_H": -0.4, "kappa_mean": -0.2}

    def fake_ingestor(path: Path) -> list[Ticker]:
        assert path == csv_path
        calls["ingestor"] = True
        return [_make_tick(101), _make_tick(102)]

    def fake_signal_builder(metrics: dict[str, float], window: int):
        assert metrics["delta_H"] == -0.4
        assert window == 5
        calls["signal_builder"] = True

        def _signal(prices: np.ndarray) -> np.ndarray:
            return np.ones_like(prices)

        return _signal

    def fake_backtester(prices: np.ndarray, signal_fn, fee: float) -> Result:
        np.testing.assert_allclose(prices, np.array([101.0, 102.0]))
        np.testing.assert_allclose(signal_fn(prices), np.ones(2))
        assert fee == 0.001
        calls["backtester"] = True
        return Result(pnl=1.5, max_dd=0.1, trades=2, equity_curve=np.array([1.0, 1.2]))

    output_dir = tmp_path / "artifacts"
    pipeline = SmokeE2EPipeline(
        analyzer=fake_analyzer,
        ingestor=fake_ingestor,
        signal_builder=fake_signal_builder,
        backtester=fake_backtester,
        artifact_writer=write_summary,
    )

    config = SmokeE2EConfig(
        csv_path=csv_path,
        output_dir=output_dir,
        seed=7,
        fee=0.001,
        momentum_window=5,
    )

    run = pipeline.run(config)

    assert run.seed == 7
    assert run.ingested_ticks == 2
    assert dict(run.metrics)["kappa_mean"] == -0.2
    assert calls == {
        "analyzer": True,
        "ingestor": True,
        "signal_builder": True,
        "backtester": True,
    }

    summary_path = run.artifacts.summary_path
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["seed"] == 7
    assert payload["backtest"]["pnl"] == 1.5
    assert payload["backtest"]["trades"] == 2
