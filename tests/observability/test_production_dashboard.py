from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from observability.dashboard import ProductionDashboardBuilder, ProductionTelemetryStore
from observability.dashboard.store import AlertRecord


class _DummyKillSwitch:
    def __init__(self, enabled: bool, reason: str) -> None:
        self._enabled = enabled
        self._reason = reason

    def is_triggered(self) -> bool:
        return self._enabled

    @property
    def reason(self) -> str:
        return self._reason


class _DummyRiskManager:
    def __init__(self) -> None:
        self.kill_switch = _DummyKillSwitch(enabled=False, reason="")
        self._realized_pnl = 12_500.5
        self._unrealized_pnl = -320.75
        self._current_drawdown = 0.031

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def unrealized_pnl(self) -> float:
        return self._unrealized_pnl

    @property
    def current_drawdown(self) -> float:
        return self._current_drawdown


def _load_store() -> ProductionTelemetryStore:
    path = Path(__file__).with_suffix("").parent / "data" / "production_snapshot.json"
    return ProductionTelemetryStore.from_path(path)


def test_store_parsing_and_snapshot() -> None:
    store = _load_store()
    snapshot = store.snapshot()
    assert snapshot["kill_switch_events"] == 2
    assert snapshot["circuit_events"] == 2
    assert snapshot["exposure_samples"] == 3
    assert store.latest_kill_switch_event() is not None
    assert store.latest_circuit_event() is not None


def test_dashboard_builder_composes_payload() -> None:
    store = _load_store()
    builder = ProductionDashboardBuilder(
        risk_manager=_DummyRiskManager(),
        telemetry_store=store,
        default_environment="prod",
        default_currency="USD",
    )

    dashboard = builder.build()
    assert dashboard.environment == "prod"
    controls = dashboard.controls
    assert controls["killSwitch"]["enabled"] is False
    assert controls["circuitBreaker"]["state"] == "closed"

    metrics = dashboard.metrics
    gross_exposure = metrics["grossExposure"]
    assert gross_exposure["value"] == 1_230_000.0
    assert round(gross_exposure["trend"], 2) == 110000.0

    pnl = metrics["pnl"]
    assert pnl["realized"] == 12_500.5
    assert pnl["unrealized"] == -320.75

    series = dashboard.time_series
    assert len(series["exposure"]) == 3
    assert len(series["drawdown"]) == 3

    alerts = list(dashboard.alerts)
    assert alerts[0]["id"] == "cb-open"
    assert alerts[0]["severity"] == "warning"
    assert alerts[0]["message"].startswith("Circuit breaker")


def test_store_handles_missing_snapshot_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "does_not_exist.json"
    store = ProductionTelemetryStore.from_path(missing_path)
    snapshot = store.snapshot()
    assert snapshot == {
        "kill_switch_events": 0,
        "circuit_events": 0,
        "exposure_samples": 0,
        "drawdown_samples": 0,
        "order_samples": 0,
        "alerts": 0,
    }


def test_store_from_payload_rejects_invalid_timestamp() -> None:
    payload = {"controls": {"kill_switch": [{"enabled": True, "timestamp": "yesterday"}]}}
    with pytest.raises(ValueError):
        ProductionTelemetryStore.from_payload(payload)


def test_store_normalises_alert_severity() -> None:
    timestamp = datetime.now(timezone.utc)
    store = ProductionTelemetryStore()
    store.record_alert(
        AlertRecord(
            severity="CRITICAL",
            message="Test alert",
            timestamp=timestamp,
            identifier=None,
        )
    )
    [alert] = store.alerts()
    assert alert.severity == "critical"


def test_dashboard_builder_defaults_for_empty_store() -> None:
    store = ProductionTelemetryStore()
    builder = ProductionDashboardBuilder(
        risk_manager=None,
        telemetry_store=store,
        default_environment="prod",
        default_currency="USD",
    )

    dashboard = builder.build()
    assert dashboard.environment == "prod"
    kill_switch = dashboard.controls["killSwitch"]
    assert kill_switch["enabled"] is None
    assert kill_switch["previous"]["enabled"] is None
    assert dashboard.controls["circuitBreaker"]["state"] == "unknown"
    assert dashboard.metrics["grossExposure"]["value"] is None
    assert dashboard.metrics["orders"]["open"] is None
    assert dashboard.alerts == []
