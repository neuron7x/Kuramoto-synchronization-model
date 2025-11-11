"""Typed storage for production dashboard telemetry snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, MutableSequence, Sequence

import json

__all__ = [
    "AlertRecord",
    "CircuitBreakerEvent",
    "ExposureSample",
    "DrawdownSample",
    "KillSwitchEvent",
    "OrderHealthSample",
    "ProductionTelemetryStore",
]


@dataclass(slots=True, frozen=True)
class KillSwitchEvent:
    """State transition captured when the global kill switch changes."""

    enabled: bool
    timestamp: datetime
    actor: str | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class CircuitBreakerEvent:
    """State transition emitted by the circuit breaker guard."""

    state: str
    timestamp: datetime
    reason: str | None = None
    cooldown_seconds: int | None = None


@dataclass(slots=True, frozen=True)
class ExposureSample:
    """Gross exposure observation normalised for dashboard use."""

    value: float
    timestamp: datetime
    limit: float | None = None


@dataclass(slots=True, frozen=True)
class DrawdownSample:
    """Drawdown observation normalised for dashboard use."""

    value: float
    timestamp: datetime
    limit: float | None = None


@dataclass(slots=True, frozen=True)
class OrderHealthSample:
    """Order-health snapshot summarising flow, rejections, and trips."""

    open_orders: int | None
    rejection_rate: float | None
    circuit_trips: int | None
    timestamp: datetime
    window: str | None = None


@dataclass(slots=True, frozen=True)
class AlertRecord:
    """Alert surfaced on the dashboard."""

    severity: str
    message: str
    timestamp: datetime
    identifier: str | None = None


class ProductionTelemetryStore:
    """Container providing deterministic access to dashboard snapshots."""

    def __init__(
        self,
        *,
        kill_switch_events: Iterable[KillSwitchEvent] | None = None,
        circuit_events: Iterable[CircuitBreakerEvent] | None = None,
        exposure_samples: Iterable[ExposureSample] | None = None,
        drawdown_samples: Iterable[DrawdownSample] | None = None,
        order_samples: Iterable[OrderHealthSample] | None = None,
        alerts: Iterable[AlertRecord] | None = None,
    ) -> None:
        self._kill_switch_events: MutableSequence[KillSwitchEvent] = []
        self._circuit_events: MutableSequence[CircuitBreakerEvent] = []
        self._exposure_samples: MutableSequence[ExposureSample] = []
        self._drawdown_samples: MutableSequence[DrawdownSample] = []
        self._order_samples: MutableSequence[OrderHealthSample] = []
        self._alerts: MutableSequence[AlertRecord] = []

        for event in kill_switch_events or ():
            self.record_kill_switch_event(event)
        for event in circuit_events or ():
            self.record_circuit_event(event)
        for sample in exposure_samples or ():
            self.record_exposure(sample)
        for sample in drawdown_samples or ():
            self.record_drawdown(sample)
        for sample in order_samples or ():
            self.record_order_health(sample)
        for alert in alerts or ():
            self.record_alert(alert)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _sort_by_timestamp(sequence: MutableSequence) -> None:
        sequence.sort(key=lambda entry: getattr(entry, "timestamp", datetime.now(timezone.utc)))

    def record_kill_switch_event(self, event: KillSwitchEvent) -> None:
        self._kill_switch_events.append(event)
        self._sort_by_timestamp(self._kill_switch_events)

    def record_circuit_event(self, event: CircuitBreakerEvent) -> None:
        normalised_state = event.state.replace(" ", "_").lower()
        self._circuit_events.append(
            CircuitBreakerEvent(
                state=normalised_state,
                timestamp=event.timestamp,
                reason=event.reason,
                cooldown_seconds=event.cooldown_seconds,
            )
        )
        self._sort_by_timestamp(self._circuit_events)

    def record_exposure(self, sample: ExposureSample) -> None:
        self._exposure_samples.append(sample)
        self._sort_by_timestamp(self._exposure_samples)

    def record_drawdown(self, sample: DrawdownSample) -> None:
        self._drawdown_samples.append(sample)
        self._sort_by_timestamp(self._drawdown_samples)

    def record_order_health(self, sample: OrderHealthSample) -> None:
        self._order_samples.append(sample)
        self._sort_by_timestamp(self._order_samples)

    def record_alert(self, alert: AlertRecord) -> None:
        normalised = AlertRecord(
            severity=alert.severity.lower(),
            message=alert.message,
            timestamp=alert.timestamp,
            identifier=alert.identifier,
        )
        self._alerts.append(normalised)
        self._sort_by_timestamp(self._alerts)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    def latest_kill_switch_event(self) -> KillSwitchEvent | None:
        return self._kill_switch_events[-1] if self._kill_switch_events else None

    def previous_kill_switch_event(self) -> KillSwitchEvent | None:
        return self._kill_switch_events[-2] if len(self._kill_switch_events) >= 2 else None

    def latest_circuit_event(self) -> CircuitBreakerEvent | None:
        return self._circuit_events[-1] if self._circuit_events else None

    def exposure_series(self) -> list[ExposureSample]:
        return list(self._exposure_samples)

    def drawdown_series(self) -> list[DrawdownSample]:
        return list(self._drawdown_samples)

    def order_series(self) -> list[OrderHealthSample]:
        return list(self._order_samples)

    def latest_orders(self) -> OrderHealthSample | None:
        return self._order_samples[-1] if self._order_samples else None

    def latest_exposure(self) -> ExposureSample | None:
        return self._exposure_samples[-1] if self._exposure_samples else None

    def latest_drawdown(self) -> DrawdownSample | None:
        return self._drawdown_samples[-1] if self._drawdown_samples else None

    def alerts(self) -> list[AlertRecord]:
        return list(self._alerts)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_timestamp(payload: Mapping[str, object]) -> datetime:
        raw = payload.get("timestamp")
        if raw is None:
            raise ValueError("timestamp is required for telemetry records")
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:  # pragma: no cover - defensive
                raise ValueError(f"Invalid timestamp value: {raw!r}") from exc
        raise TypeError(f"Unsupported timestamp type: {type(raw)!r}")

    @classmethod
    def _parse_controls(cls, payload: Mapping[str, object], store: "ProductionTelemetryStore") -> None:
        controls = payload.get("controls")
        if not isinstance(controls, Mapping):
            return

        for entry in controls.get("kill_switch", []) if isinstance(controls.get("kill_switch"), Sequence) else []:
            if not isinstance(entry, Mapping):
                continue
            store.record_kill_switch_event(
                KillSwitchEvent(
                    enabled=bool(entry.get("enabled", False)),
                    timestamp=cls._coerce_timestamp(entry),
                    actor=(str(entry.get("actor")) if entry.get("actor") is not None else None),
                    reason=(str(entry.get("reason")) if entry.get("reason") is not None else None),
                )
            )

        for entry in controls.get("circuit_breaker", []) if isinstance(controls.get("circuit_breaker"), Sequence) else []:
            if not isinstance(entry, Mapping):
                continue
            cooldown_raw = entry.get("cooldown_seconds")
            cooldown = None
            if cooldown_raw is not None:
                try:
                    cooldown = int(cooldown_raw)
                except (TypeError, ValueError):
                    cooldown = None
            store.record_circuit_event(
                CircuitBreakerEvent(
                    state=str(entry.get("state", "unknown")),
                    timestamp=cls._coerce_timestamp(entry),
                    reason=(str(entry.get("reason")) if entry.get("reason") is not None else None),
                    cooldown_seconds=cooldown,
                )
            )

    @classmethod
    def _parse_metrics(cls, payload: Mapping[str, object], store: "ProductionTelemetryStore") -> None:
        metrics = payload.get("metrics")
        if not isinstance(metrics, Mapping):
            return

        def _iter_records(key: str) -> Sequence[Mapping[str, object]]:
            value = metrics.get(key)
            if isinstance(value, Sequence):
                return [entry for entry in value if isinstance(entry, Mapping)]
            return []

        for entry in _iter_records("exposure"):
            limit = entry.get("limit")
            store.record_exposure(
                ExposureSample(
                    value=float(entry.get("value", 0.0)),
                    timestamp=cls._coerce_timestamp(entry),
                    limit=float(limit) if limit is not None else None,
                )
            )

        for entry in _iter_records("drawdown"):
            limit = entry.get("limit")
            store.record_drawdown(
                DrawdownSample(
                    value=float(entry.get("value", 0.0)),
                    timestamp=cls._coerce_timestamp(entry),
                    limit=float(limit) if limit is not None else None,
                )
            )

        for entry in _iter_records("orders"):
            window = entry.get("window")
            window_str = str(window) if window is not None else None
            open_orders = entry.get("open")
            rejection_rate = entry.get("rejection_rate")
            circuit_trips = entry.get("circuit_trips")
            store.record_order_health(
                OrderHealthSample(
                    open_orders=int(open_orders) if open_orders is not None else None,
                    rejection_rate=float(rejection_rate) if rejection_rate is not None else None,
                    circuit_trips=int(circuit_trips) if circuit_trips is not None else None,
                    window=window_str,
                    timestamp=cls._coerce_timestamp(entry),
                )
            )

    @classmethod
    def _parse_alerts(cls, payload: Mapping[str, object], store: "ProductionTelemetryStore") -> None:
        alerts = payload.get("alerts")
        if not isinstance(alerts, Sequence):
            return
        for entry in alerts:
            if not isinstance(entry, Mapping):
                continue
            store.record_alert(
                AlertRecord(
                    severity=str(entry.get("severity", "info")),
                    message=str(entry.get("message", "")),
                    timestamp=cls._coerce_timestamp(entry),
                    identifier=(str(entry.get("id")) if entry.get("id") is not None else None),
                )
            )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ProductionTelemetryStore":
        """Hydrate a store from a dictionary payload."""

        store = cls()
        cls._parse_controls(payload, store)
        cls._parse_metrics(payload, store)
        cls._parse_alerts(payload, store)
        return store

    @classmethod
    def from_path(cls, path: Path | str | None) -> "ProductionTelemetryStore":
        """Load telemetry from a JSON file when available."""

        if path is None:
            return cls()
        resolved = Path(path).expanduser()
        if not resolved.exists():
            return cls()
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("Telemetry snapshot must be a JSON object")
        return cls.from_payload(payload)

    # ------------------------------------------------------------------
    # Snapshot helpers used for diagnostics
    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, object]:
        """Return lightweight statistics used for debugging."""

        return {
            "kill_switch_events": len(self._kill_switch_events),
            "circuit_events": len(self._circuit_events),
            "exposure_samples": len(self._exposure_samples),
            "drawdown_samples": len(self._drawdown_samples),
            "order_samples": len(self._order_samples),
            "alerts": len(self._alerts),
        }
