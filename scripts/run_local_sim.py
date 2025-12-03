"""Offline safe-mode simulation runner for TradePulse.

This module assembles a minimal-yet-representative trading loop that can be
executed without touching external exchanges, credentials, or networks.  The
entry-point :func:`run_local_sim` showcases the data ingestion, signal
construction, risk gating, and execution hand-off flow using deterministic
mocks so stakeholders can observe the full decision lifecycle safely.

Typical usage (from a Python shell or script) ::

    from scripts.run_local_sim import run_local_sim, SimulationConfig

    result = run_local_sim()
    print(result.summary())

Developers can override the price source or risk parameters by instantiating a
custom :class:`SimulationConfig`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, MutableMapping

import numpy as np
import pandas as pd

from core.indicators.kuramoto_ricci_composite import (
    CompositeSignal,
    TradePulseCompositeEngine,
)
from domain import Order, OrderSide, OrderType, Signal, SignalAction
from execution.audit import ExecutionAuditLogger, get_execution_audit_logger
from execution.connectors import SimulatedExchangeConnector
from execution.paper_trading import (
    DeterministicLatencyModel,
    PaperOrderReport,
    PaperTradingEngine,
)
from execution.risk import (
    LimitViolation,
    OrderRateExceeded,
    RiskError,
    RiskLimits,
    RiskManager,
)

LOGGER = logging.getLogger("tradepulse.local_sim")


@dataclass(slots=True, frozen=True)
class RiskCheckResult:
    """Outcome of a risk validation attempt."""

    status: str
    reason: str | None = None
    kill_switch_engaged: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "kill_switch_engaged": self.kill_switch_engaged,
        }


@dataclass(slots=True)
class SimulationConfig:
    """Configuration controlling :func:`run_local_sim` behaviour."""

    symbol: str = "MOCK-USD"
    price_source: Path | None = None
    history_length: int = 720
    price_frequency: str = "1min"
    initial_price: float = 1_000.0
    drift: float = 0.0008
    volatility: float = 0.015
    volume_mean: float = 8.5
    volume_sigma: float = 0.35
    entry_threshold: float = 0.05
    base_order_size: float = 1.0
    risk_limits: RiskLimits = field(
        default_factory=lambda: RiskLimits(
            max_notional=250_000.0,
            max_position=25.0,
            max_orders_per_interval=10,
            interval_seconds=60.0,
            kill_switch_limit_multiplier=2.0,
        )
    )
    audit_path: Path | None = None


@dataclass(slots=True)
class SimulationResult:
    """Structured artefacts produced by :func:`run_local_sim`."""

    prices: pd.DataFrame
    composite_signal: CompositeSignal
    signal: Signal
    risk_check: RiskCheckResult
    order: Order | None
    execution_report: PaperOrderReport | None
    audit_log_path: Path

    def summary(self) -> Mapping[str, object]:
        """Return a JSON-serialisable snapshot of the simulation."""

        payload: MutableMapping[str, object] = {
            "symbol": self.signal.symbol,
            "signal_action": self.signal.action.value,
            "signal_confidence": float(self.signal.confidence),
            "signal_metadata": dict(self.signal.metadata or {}),
            "risk": self.risk_check.to_dict(),
            "audit_log_path": str(self.audit_log_path),
        }
        if self.order is not None:
            payload["order"] = {
                "side": self.order.side.value,
                "quantity": float(self.order.quantity),
                "order_type": self.order.order_type.value,
            }
        if self.execution_report is not None:
            payload["execution"] = {
                "order_id": self.execution_report.order_id,
                "fills": [
                    {
                        "price": fill.price,
                        "quantity": fill.quantity,
                        "timestamp": fill.timestamp,
                    }
                    for fill in self.execution_report.fills
                ],
                "latency_total": self.execution_report.latency.total_delay,
                "pnl_deviation": self.execution_report.pnl.deviation,
            }
        return payload


def _load_prices(config: SimulationConfig) -> pd.DataFrame:
    source = config.price_source or Path("sample.csv")
    if source.exists():
        df = pd.read_csv(source, index_col=0, parse_dates=True)
        df = df.rename(columns={col: col.lower() for col in df.columns})
        required = {"close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Mock price source missing columns: {sorted(missing)}")
        df = df.sort_index()
        if len(df) >= config.history_length:
            return df.tail(config.history_length)
    else:
        df = pd.DataFrame()

    length = max(config.history_length, 2)
    index = pd.date_range(
        end=datetime.now(timezone.utc),
        periods=length,
        freq=config.price_frequency,
    )
    rng = np.random.default_rng(7)
    drift = config.drift
    volatility = config.volatility
    shocks = rng.normal(loc=drift, scale=volatility, size=length)
    log_prices = np.log(config.initial_price) + np.cumsum(shocks)
    prices = np.exp(log_prices)
    volume = rng.lognormal(
        mean=config.volume_mean, sigma=config.volume_sigma, size=length
    )
    mock = pd.DataFrame({"close": prices, "volume": volume}, index=index)
    if not df.empty:
        mock = pd.concat([df, mock]).tail(config.history_length)
    return mock


def _build_signal(
    df: pd.DataFrame, config: SimulationConfig
) -> tuple[CompositeSignal, Signal]:
    engine = TradePulseCompositeEngine()
    composite = engine.analyze_market(df)
    entry = float(composite.entry_signal)
    exit_level = float(composite.exit_signal)
    action: SignalAction
    if entry > config.entry_threshold:
        action = SignalAction.BUY
    elif entry < -config.entry_threshold:
        action = SignalAction.SELL
    elif exit_level > 0.6:
        action = SignalAction.EXIT
    else:
        action = SignalAction.HOLD

    metadata: dict[str, object] = {
        "phase": composite.phase.value,
        "entry_signal": entry,
        "exit_signal": exit_level,
        "risk_multiplier": float(composite.risk_multiplier),
        "dominant_timeframe": composite.dominant_timeframe_sec,
    }
    if composite.skipped_timeframes:
        metadata["skipped_timeframes"] = list(composite.skipped_timeframes)

    signal = Signal(
        symbol=config.symbol,
        action=action,
        confidence=float(composite.confidence),
        timestamp=composite.timestamp.to_pydatetime(),
        rationale=f"Composite phase {composite.phase.value}",
        metadata=metadata,
    )
    return composite, signal


def _derive_order_quantity(
    signal: Signal, config: SimulationConfig, price: float
) -> float:
    magnitude = abs(float(signal.metadata.get("entry_signal", 0.0)))
    risk_multiplier = float(signal.metadata.get("risk_multiplier", 1.0))
    scaled = config.base_order_size * max(magnitude, config.entry_threshold)
    qty = scaled * risk_multiplier
    if price <= 0:
        return qty
    max_qty = config.risk_limits.max_notional / max(price, 1e-9)
    return float(min(qty, max_qty))


def _acquire_audit_logger(config: SimulationConfig) -> ExecutionAuditLogger:
    if config.audit_path is not None:
        return ExecutionAuditLogger(config.audit_path)
    return get_execution_audit_logger()


def run_local_sim(config: SimulationConfig | None = None) -> SimulationResult:
    """Execute a single offline trading simulation cycle."""

    cfg = config or SimulationConfig()
    LOGGER.info("Starting offline simulation", extra={"event": "sim.start"})

    prices = _load_prices(cfg)
    LOGGER.info(
        "Loaded price series", extra={"event": "sim.prices_loaded", "rows": len(prices)}
    )

    composite, signal = _build_signal(prices, cfg)
    LOGGER.info(
        "Generated signal",
        extra={
            "event": "sim.signal",
            "action": signal.action.value,
            "confidence": float(signal.confidence),
            "entry": signal.metadata.get("entry_signal"),
        },
    )

    audit_logger = _acquire_audit_logger(cfg)
    risk_manager = RiskManager(cfg.risk_limits, audit_logger=audit_logger)
    risk_result = RiskCheckResult(status="skipped")

    order: Order | None = None
    execution_report: PaperOrderReport | None = None

    last_price = float(prices["close"].iloc[-1])

    if signal.action in {SignalAction.BUY, SignalAction.SELL}:
        side = OrderSide.BUY if signal.action is SignalAction.BUY else OrderSide.SELL
        quantity = _derive_order_quantity(signal, cfg, last_price)
        order = Order(
            symbol=cfg.symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
        )
        try:
            risk_manager.validate_order(
                order.symbol, order.side.value, order.quantity, last_price
            )
        except (LimitViolation, OrderRateExceeded) as exc:
            LOGGER.warning(
                "Risk check rejected order",
                extra={"event": "sim.risk_reject", "reason": str(exc)},
            )
            risk_result = RiskCheckResult(
                status="rejected", reason=str(exc), kill_switch_engaged=False
            )
        except RiskError as exc:
            LOGGER.error(
                "Kill-switch blocked order",
                extra={"event": "sim.risk_block", "reason": str(exc)},
            )
            risk_result = RiskCheckResult(
                status="blocked", reason=str(exc), kill_switch_engaged=True
            )
        else:
            risk_result = RiskCheckResult(status="passed", kill_switch_engaged=False)
            engine = PaperTradingEngine(
                SimulatedExchangeConnector(),
                latency_model=DeterministicLatencyModel(
                    ack_delay=0.05, fill_delay=0.15
                ),
            )
            execution_report = engine.execute_order(
                order,
                execution_price=last_price,
                metadata={"simulation": True, "phase": signal.metadata.get("phase")},
            )
            fill_side = "buy" if order.side is OrderSide.BUY else "sell"
            risk_manager.register_fill(
                order.symbol, fill_side, order.quantity, last_price
            )
            LOGGER.info(
                "Executed simulated order",
                extra={
                    "event": "sim.executed",
                    "order_id": execution_report.order_id,
                    "fills": len(execution_report.fills),
                },
            )
    else:
        LOGGER.info(
            "No actionable signal",
            extra={"event": "sim.no_action", "action": signal.action.value},
        )

    audit_path = audit_logger.path

    LOGGER.info(
        "Simulation complete",
        extra={
            "event": "sim.complete",
            "risk_status": risk_result.status,
            "audit_path": str(audit_path),
        },
    )

    return SimulationResult(
        prices=prices,
        composite_signal=composite,
        signal=signal,
        risk_check=risk_result,
        order=order,
        execution_report=execution_report,
        audit_log_path=audit_path,
    )


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    result = run_local_sim()
    for key, value in result.summary().items():
        LOGGER.info("%s: %s", key, value)
