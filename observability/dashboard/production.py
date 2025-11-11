"""Builders that hydrate the production dashboard payload."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping

from execution.risk import RiskManager

from .store import (
    AlertRecord,
    DrawdownSample,
    ExposureSample,
    OrderHealthSample,
    ProductionTelemetryStore,
)

__all__ = ["ProductionDashboardBuilder", "MonitoringDashboard"]


@dataclass(slots=True)
class MonitoringDashboard:
    """Structured monitoring payload expected by the UI layer."""

    environment: str
    currency: str
    controls: Mapping[str, Mapping[str, object]]
    metrics: Mapping[str, object]
    time_series: Mapping[str, Iterable[Mapping[str, object]]]
    alerts: Iterable[Mapping[str, object]]


def _to_timestamp(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


class ProductionDashboardBuilder:
    """Aggregate telemetry sources into a monitoring dashboard payload."""

    def __init__(
        self,
        *,
        risk_manager: RiskManager | None,
        telemetry_store: ProductionTelemetryStore,
        default_environment: str = "prod",
        default_currency: str = "USD",
    ) -> None:
        self._risk_manager = risk_manager
        self._store = telemetry_store
        self._environment = default_environment
        self._currency = default_currency

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self, *, environment: str | None = None, currency: str | None = None) -> MonitoringDashboard:
        env_label = environment or self._environment
        currency_label = currency or self._currency

        controls = {
            "killSwitch": self._build_kill_switch_block(),
            "circuitBreaker": self._build_circuit_block(),
        }
        metrics = self._build_metrics_block()
        time_series = self._build_series_block()
        alerts = [self._serialise_alert(alert) for alert in self._store.alerts()]

        return MonitoringDashboard(
            environment=env_label,
            currency=currency_label,
            controls=controls,
            metrics=metrics,
            time_series=time_series,
            alerts=alerts,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_kill_switch_block(self) -> Mapping[str, object]:
        event = self._store.latest_kill_switch_event()
        previous = self._store.previous_kill_switch_event()
        kill_switch = getattr(self._risk_manager, "kill_switch", None)
        engaged = bool(kill_switch.is_triggered()) if kill_switch is not None else (event.enabled if event else None)
        reason = None
        if kill_switch is not None:
            reason = kill_switch.reason or None
        elif event is not None:
            reason = event.reason
        actor = event.actor if event is not None else None
        changed_at = event.timestamp if event is not None else None

        return {
            "enabled": engaged,
            "changedAt": _to_timestamp(changed_at),
            "changedBy": actor,
            "reason": reason,
            "previous": {
                "enabled": previous.enabled if previous else None,
                "timestamp": _to_timestamp(previous.timestamp if previous else None),
            },
        }

    def _build_circuit_block(self) -> Mapping[str, object]:
        event = self._store.latest_circuit_event()
        if event is None:
            return {"state": "unknown"}
        return {
            "state": event.state,
            "triggeredAt": _to_timestamp(event.timestamp),
            "reason": event.reason,
            "cooldownSeconds": event.cooldown_seconds,
        }

    def _build_metrics_block(self) -> Mapping[str, object]:
        exposure = self._store.exposure_series()
        drawdown = self._store.drawdown_series()
        orders = self._store.latest_orders()

        def _compute_trend(samples: list[ExposureSample | DrawdownSample]) -> float | None:
            if len(samples) < 2:
                return None
            first = samples[0].value
            last = samples[-1].value
            return float(last - first)

        exposure_latest = exposure[-1] if exposure else None
        drawdown_latest = drawdown[-1] if drawdown else None

        return {
            "grossExposure": {
                "value": exposure_latest.value if exposure_latest else None,
                "limit": exposure_latest.limit if exposure_latest else None,
                "trend": _compute_trend(exposure) if exposure else None,
            },
            "drawdown": {
                "value": drawdown_latest.value if drawdown_latest else None,
                "limit": drawdown_latest.limit if drawdown_latest else None,
                "trend": _compute_trend(drawdown) if drawdown else None,
            },
            "orders": self._serialise_orders(orders),
            "pnl": self._build_pnl_block(),
        }

    def _serialise_orders(self, sample: OrderHealthSample | None) -> Mapping[str, object]:
        if sample is None:
            return {"open": None, "rejectionRate": None, "circuitTrips": None, "window": None}
        return {
            "open": sample.open_orders,
            "rejectionRate": sample.rejection_rate,
            "circuitTrips": sample.circuit_trips,
            "window": sample.window,
            "timestamp": _to_timestamp(sample.timestamp),
        }

    def _build_pnl_block(self) -> Mapping[str, object]:
        manager = self._risk_manager
        realized = getattr(manager, "realized_pnl", None)
        unrealized = getattr(manager, "unrealized_pnl", None)
        drawdown = getattr(manager, "current_drawdown", None)
        return {
            "realized": float(realized) if realized is not None else None,
            "unrealized": float(unrealized) if unrealized is not None else None,
            "drawdown": float(drawdown) if drawdown is not None else None,
        }

    def _build_series_block(self) -> Mapping[str, Iterable[Mapping[str, object]]]:
        exposure_series = [self._serialise_point(sample) for sample in self._store.exposure_series()]
        drawdown_series = [self._serialise_point(sample) for sample in self._store.drawdown_series()]
        return {
            "exposure": exposure_series,
            "drawdown": drawdown_series,
        }

    def _serialise_point(self, sample: ExposureSample | DrawdownSample) -> Mapping[str, object]:
        return {
            "timestamp": _to_timestamp(sample.timestamp),
            "value": sample.value,
            "limit": sample.limit,
        }

    def _serialise_alert(self, alert: AlertRecord) -> Mapping[str, object]:
        return {
            "id": alert.identifier or self._derive_alert_id(alert),
            "severity": alert.severity,
            "message": alert.message,
            "timestamp": _to_timestamp(alert.timestamp),
        }

    @staticmethod
    def _derive_alert_id(alert: AlertRecord) -> str:
        stamp = _to_timestamp(alert.timestamp) or 0
        return f"alert-{alert.severity}-{stamp}"
