from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import pytest

from backtest.engine import walk_forward
from domain import Order, OrderSide, OrderType
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import LimitViolation, RiskLimits, RiskManager
from interfaces.cli import signal_from_indicators
from tests.fixtures.fake_exchange import FakeExchangeAdapter

pytestmark = pytest.mark.integration


def _wait_for(predicate, *, timeout: float, interval: float = 0.05) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("condition was not met within timeout")


def _orders_drained(loop: LiveExecutionLoop, venue: str) -> bool:
    context = loop._contexts[venue]  # type: ignore[attr-defined]
    queue = getattr(context.oms, "_queue", None)
    if queue and len(queue) > 0:
        return False
    return not any(order.is_active for order in context.oms.outstanding())


def run_backtest_and_export_signals(
    config: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    data_path = Path(config["data_path"])
    if not data_path.exists():
        raise FileNotFoundError(f"data source missing: {data_path}")
    price_col = str(config.get("price_col", "price"))
    ts_col = str(config.get("timestamp_col", "ts"))
    df = pd.read_csv(data_path)
    limit = int(config.get("limit", 0))
    if limit > 0 and limit < len(df):
        df = df.iloc[:limit].copy()
    prices = df[price_col].astype(float).to_numpy()
    timestamps = df[ts_col].astype(float).to_numpy()

    seed = int(config.get("seed", 0))
    np.random.seed(seed)
    rng = np.random.default_rng(seed)
    _ = rng.random()  # consume deterministic sequence for parity with live run

    window = int(config.get("window", 48))
    signals = signal_from_indicators(prices, window=window, max_workers=1)
    signals = signals.astype(float)
    if np.allclose(signals, 0.0):
        momentum = np.diff(prices, prepend=prices[0])
        scale = float(np.std(momentum)) or 1.0
        zscore = momentum / scale
        fallback = np.where(zscore > 0.5, 1.0, np.where(zscore < -0.5, -1.0, 0.0))
        fallback[0] = 0.0
        signals = fallback.astype(float)

    def _signal_fn(_: np.ndarray) -> np.ndarray:
        return signals

    fee = float(config.get("fee", 0.0))
    strategy_name = str(config.get("strategy_name", "integration_replay"))
    result = walk_forward(prices, _signal_fn, fee=fee, strategy_name=strategy_name)

    orders: list[dict[str, float | str | int]] = []
    current = 0.0
    for idx, target in enumerate(signals):
        target_value = float(target)
        delta = target_value - current
        price = float(prices[idx])
        if abs(delta) > 1e-9:
            side = "buy" if delta > 0 else "sell"
            orders.append(
                {
                    "index": idx,
                    "ts": float(timestamps[idx]),
                    "side": side,
                    "qty": abs(delta),
                    "price": price,
                    "target": target_value,
                }
            )
            current = target_value
        else:
            current = target_value

    signal_records = [
        {
            "index": idx,
            "ts": float(timestamps[idx]),
            "target": float(signals[idx]),
            "price": float(prices[idx]),
        }
        for idx in range(len(signals))
    ]

    equity_curve = (
        result.equity_curve.tolist() if result.equity_curve is not None else None
    )
    report = {
        "pnl": float(result.pnl),
        "max_drawdown": float(result.max_dd),
        "trades": int(result.trades),
        "latency_steps": int(result.latency_steps),
        "equity_curve": equity_curve,
    }

    payload = {
        "meta": {
            "seed": seed,
            "symbol": str(config.get("symbol", "SAMPLE-USD")),
            "window": window,
            "fee": fee,
        },
        "prices": [float(x) for x in prices],
        "timestamps": [float(x) for x in timestamps],
        "signals": [float(x) for x in signals],
        "orders": orders,
        "backtest_report": report,
        "signal_records": signal_records,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "signals": signals,
        "report": report,
        "prices": prices,
        "timestamps": timestamps,
        "orders": orders,
    }


def run_live_runner_with_fake_exchange(
    signals_path: Path,
    fake_exchange_cfg: Mapping[str, Any],
    risk_limits: RiskLimits,
    *,
    timeout_seconds: float = 30.0,
    debug_dir: Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(signals_path.read_text(encoding="utf-8"))
    prices = np.asarray(payload["prices"], dtype=float)
    signals = np.asarray(payload["signals"], dtype=float)
    timestamps = np.asarray(payload["timestamps"], dtype=float)
    symbol = str(payload.get("meta", {}).get("symbol", "SAMPLE-USD"))

    if timestamps.size > 1:
        deltas = np.diff(timestamps)
        assert np.all(deltas >= 0), "timestamps must be monotonic"

    artifacts: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="live-sim-") as tmpdir:
        base = Path(tmpdir)
        state_dir = base / "state"
        ledger_dir = base / "ledger"
        config = LiveLoopConfig(
            state_dir=state_dir,
            ledger_dir=ledger_dir,
            submission_interval=0.02,
            fill_poll_interval=0.05,
            heartbeat_interval=0.1,
            max_backoff=0.5,
        )
        adapter = FakeExchangeAdapter(**fake_exchange_cfg)
        risk_manager = RiskManager(risk_limits)
        loop = LiveExecutionLoop({"fake": adapter}, risk_manager, config=config)
        context = loop._contexts["fake"]  # type: ignore[attr-defined]
        context.oms.config.auto_persist = False
        context.oms.config.ledger_path = None
        setattr(context.oms, "_ledger", None)
        loop.start(cold_start=True)
        executed_positions: list[float] = []
        limit_violations = 0

        try:
            current_position = risk_manager.current_position(symbol)
            for idx, target in enumerate(signals):
                target_value = float(target)
                delta = target_value - current_position
                price = float(prices[idx])
                expected_position = current_position
                if abs(delta) > 1e-9:
                    side = OrderSide.BUY if delta > 0 else OrderSide.SELL
                    order = Order(
                        symbol=symbol,
                        side=side,
                        quantity=abs(delta),
                        price=price,
                        order_type=OrderType.MARKET,
                    )
                    correlation_id = f"sig-{idx}"
                    try:
                        loop.submit_order("fake", order, correlation_id=correlation_id)
                        expected_position = target_value
                    except LimitViolation:
                        limit_violations += 1
                        expected_position = current_position
                _wait_for(
                    lambda: _orders_drained(loop, "fake"),
                    timeout=timeout_seconds,
                )
                settle_deadline = time.monotonic() + min(timeout_seconds, 1.0)
                while time.monotonic() < settle_deadline:
                    settled_position = risk_manager.current_position(symbol)
                    if (
                        abs(settled_position - expected_position) <= 1e-6
                        or abs(settled_position - current_position) <= 1e-6
                    ):
                        break
                    time.sleep(0.01)
                settled_position = risk_manager.current_position(symbol)
                if abs(settled_position - expected_position) > 1e-6:
                    for fill in adapter.drain_fills():
                        risk_manager.register_fill(
                            str(fill["symbol"]),
                            str(fill["side"]),
                            float(fill["quantity"]),
                            float(fill["price"]),
                        )
                    settled_position = risk_manager.current_position(symbol)
                current_position = settled_position
                executed_positions.append(current_position)

            breach_order = Order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=abs(risk_limits.max_position) * 2.0,
                price=float(prices[-1]),
                order_type=OrderType.MARKET,
            )
            try:
                loop.submit_order("fake", breach_order, correlation_id="limit-check")
            except LimitViolation:
                limit_violations += 1
            else:  # pragma: no cover - defensive guard
                raise AssertionError("Expected limit violation was not triggered")

            _wait_for(
                lambda: _orders_drained(loop, "fake"),
                timeout=timeout_seconds,
            )
        finally:
            loop.shutdown()

        positions_np = np.asarray(executed_positions, dtype=float)
        price_moves = np.diff(prices)
        if positions_np.size < 2 or price_moves.size == 0:
            pnl_steps = np.array([], dtype=float)
        else:
            positions_for_pnl = positions_np[1:]
            pnl_steps = positions_for_pnl * price_moves
        equity_curve = (
            np.concatenate(([0.0], np.cumsum(pnl_steps)))
            if pnl_steps.size
            else np.array([0.0])
        )
        pnl_total = float(pnl_steps.sum()) if pnl_steps.size else 0.0
        drawdowns = equity_curve - np.maximum.accumulate(equity_curve)
        max_drawdown = float(drawdowns.min()) if drawdowns.size else 0.0
        max_position_observed = (
            float(np.max(np.abs(positions_np))) if positions_np.size else 0.0
        )

        risk_summary = {
            "kill_switch_engaged": risk_manager.kill_switch.is_triggered(),
            "limit_violations": limit_violations,
            "current_position": risk_manager.current_position(symbol),
            "max_position_observed": max_position_observed,
        }

        live_report = {
            "pnl": pnl_total,
            "max_drawdown": max_drawdown,
            "positions": positions_np.tolist(),
            "fills": adapter.fills,
            "pnl_series": pnl_steps.tolist(),
            "equity_curve": equity_curve.tolist(),
            "risk": risk_summary,
        }

        artifacts.update({"live_report": live_report})

        if debug_dir is not None:
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_path = debug_dir / "live_report.json"
            debug_path.write_text(json.dumps(live_report, indent=2), encoding="utf-8")

    return artifacts["live_report"]


def compare_reports(
    backtest_report: Mapping[str, Any],
    live_report: Mapping[str, Any],
    signals: np.ndarray,
    *,
    pnl_tolerance_pct: float,
    position_tolerance: float,
    drawdown_tolerance: float,
    expected_max_position: float,
) -> None:
    back_pnl = float(backtest_report.get("pnl", 0.0))
    live_pnl = float(live_report.get("pnl", 0.0))
    if abs(back_pnl) > 1e-9:
        diff_pct = abs(live_pnl - back_pnl) / abs(back_pnl) * 100.0
    else:
        diff_pct = abs(live_pnl - back_pnl)
    assert (
        diff_pct <= pnl_tolerance_pct
    ), f"PnL diff too large: {diff_pct:.2f}% (tolerance {pnl_tolerance_pct}%)"

    back_dd = float(backtest_report.get("max_drawdown", 0.0))
    live_dd = float(live_report.get("max_drawdown", 0.0))
    allowed_dd = abs(back_dd) * drawdown_tolerance + 1e-6
    dd_gap = abs(abs(live_dd) - abs(back_dd))
    assert (
        dd_gap <= allowed_dd
    ), f"Drawdown mismatch {dd_gap:.4f} exceeds tolerance {allowed_dd:.4f}"

    positions = np.asarray(live_report.get("positions", []), dtype=float)
    assert positions.shape == signals.shape
    if positions.size:
        checkpoints = sorted({0, positions.size // 2, positions.size - 1})
        for idx in checkpoints:
            ref = float(signals[idx])
            obs = float(positions[idx])
            assert math.isclose(
                obs,
                ref,
                rel_tol=position_tolerance,
                abs_tol=position_tolerance,
            ), f"Position mismatch at index {idx}: expected {ref}, got {obs}"

    risk = live_report.get("risk", {})
    assert risk.get("limit_violations", 0) >= 1
    assert bool(risk.get("kill_switch_engaged", False))
    observed = float(risk.get("max_position_observed", 0.0))
    assert observed <= expected_max_position + 1e-6


def test_e2e_replayable_live_sim(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    signals_path = tmp_path / "signals.json"
    config = {
        "data_path": repo_root / "data" / "sample.csv",
        "symbol": "SAMPLE-USD",
        "seed": 1337,
        "window": 48,
        "fee": 0.0,
        "strategy_name": "integration_replay",
        "limit": 200,
    }
    backtest_payload = run_backtest_and_export_signals(config, signals_path)

    fake_cfg = {
        "latency_ms": 25,
        "jitter_ms": 10,
        "fail_rate": 0.1,
        "disconnect_rate": 0.05,
        "seed": 9001,
    }
    risk_limits = RiskLimits(
        max_notional=500_000.0,
        max_position=1.25,
        max_orders_per_interval=30,
        interval_seconds=1.0,
        kill_switch_limit_multiplier=2.0,
        kill_switch_violation_threshold=3,
        kill_switch_rate_limit_threshold=3,
    )

    debug_dir = tmp_path / "artifacts" if os.getenv("DEBUG_E2E") else None
    live_report = run_live_runner_with_fake_exchange(
        signals_path,
        fake_cfg,
        risk_limits,
        timeout_seconds=20.0,
        debug_dir=debug_dir,
    )

    compare_reports(
        backtest_payload["report"],
        live_report,
        backtest_payload["signals"],
        pnl_tolerance_pct=1.0,
        position_tolerance=0.05,
        drawdown_tolerance=0.15,
        expected_max_position=risk_limits.max_position,
    )

    assert live_report.get("fills"), "Expected at least one fill event"
