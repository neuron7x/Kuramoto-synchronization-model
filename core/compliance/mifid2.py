"""MiFID II compliance helpers for TradePulse."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

LOGGER = logging.getLogger(__name__)


def _slots_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a slotted dataclass to a dictionary.

    Args:
        obj: A dataclass instance to convert.

    Returns:
        Dictionary representation of the dataclass fields.

    Raises:
        TypeError: If the object is not a dataclass.
    """
    try:
        return {f.name: getattr(obj, f.name) for f in fields(obj)}
    except TypeError as exc:
        raise TypeError(
            f"Expected a dataclass instance, got {type(obj).__name__}"
        ) from exc


@dataclass(slots=True)
class OrderAuditTrail:
    order_id: str
    timestamp: datetime
    payload: Mapping[str, object]
    venue: str
    actor: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "order_id": self.order_id,
            "timestamp": self.timestamp.isoformat(),
            "payload": dict(self.payload),
            "venue": self.venue,
            "actor": self.actor,
        }


@dataclass(slots=True)
class ExecutionQuality:
    order_id: str
    venue: str
    price: float
    benchmark_price: float
    slippage: float
    latency_ms: float


@dataclass(slots=True)
class TransactionReport:
    order_id: str
    instrument: str
    quantity: float
    price: float
    side: str
    execution_time: datetime
    buyer: str
    seller: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "order_id": self.order_id,
            "instrument": self.instrument,
            "quantity": self.quantity,
            "price": self.price,
            "side": self.side,
            "execution_time": self.execution_time.isoformat(),
            "buyer": self.buyer,
            "seller": self.seller,
        }


@dataclass(slots=True)
class MiFID2RetentionPolicy:
    retention_years: int = 7

    def retention_delta(self) -> timedelta:
        return timedelta(days=365 * self.retention_years)


@dataclass(slots=True)
class ComplianceSnapshot:
    reports: list[TransactionReport] = field(default_factory=list)
    audit_trail: list[OrderAuditTrail] = field(default_factory=list)
    execution_quality: list[ExecutionQuality] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class MarketAbuseSignal:
    order_id: str
    actor: str
    reason: str


class MiFID2Reporter:
    """Aggregate MiFID II artefacts and export machine-readable reports."""

    def __init__(
        self,
        *,
        storage_path: Path,
        retention: MiFID2RetentionPolicy | None = None,
    ) -> None:
        self._storage_path = storage_path
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._retention = retention or MiFID2RetentionPolicy()
        self._reports: list[TransactionReport] = []
        self._audit_trail: list[OrderAuditTrail] = []
        self._execution_quality: list[ExecutionQuality] = []
        self._abuse_signals: list[MarketAbuseSignal] = []
        self._synchronised_at: datetime | None = None

    def record_order(
        self, *, order_id: str, payload: Mapping[str, object], venue: str, actor: str
    ) -> None:
        entry = OrderAuditTrail(
            order_id=order_id,
            timestamp=datetime.now(UTC),
            payload=payload,
            venue=venue,
            actor=actor,
        )
        self._audit_trail.append(entry)
        LOGGER.debug("Recorded order audit trail for %s", order_id)
        self._analyse_market_abuse(entry)

    def record_execution(
        self,
        *,
        order_id: str,
        instrument: str,
        quantity: float,
        price: float,
        side: str,
        buyer: str,
        seller: str,
        venue: str,
        benchmark_price: float,
        latency_ms: float,
    ) -> None:
        execution_time = datetime.now(UTC)
        report = TransactionReport(
            order_id=order_id,
            instrument=instrument,
            quantity=quantity,
            price=price,
            side=side,
            execution_time=execution_time,
            buyer=buyer,
            seller=seller,
        )
        quality = ExecutionQuality(
            order_id=order_id,
            venue=venue,
            price=price,
            benchmark_price=benchmark_price,
            slippage=price - benchmark_price,
            latency_ms=latency_ms,
        )
        self._reports.append(report)
        self._execution_quality.append(quality)
        LOGGER.debug("Recorded execution for %s@%s", order_id, venue)

    def synchronise_clock(self, ntp_offset_ms: float) -> None:
        self._synchronised_at = datetime.now(UTC)
        LOGGER.info("Clock synchronised with offset %.3f ms", ntp_offset_ms)

    def best_execution_breaches(
        self, threshold_bps: float = 5.0
    ) -> list[ExecutionQuality]:
        breaches = [
            quality
            for quality in self._execution_quality
            if abs(quality.slippage) > threshold_bps / 10_000 * quality.benchmark_price
        ]
        LOGGER.debug("Detected %s best execution breaches", len(breaches))
        return breaches

    def market_abuse_signals(self) -> list[MarketAbuseSignal]:
        return list(self._abuse_signals)

    def position_limit_breaches(
        self,
        *,
        positions: Mapping[str, float],
        limits: Mapping[str, float],
    ) -> dict[str, float]:
        breaches: dict[str, float] = {}
        for instrument, position in positions.items():
            limit = limits.get(instrument)
            if limit is None:
                continue
            if abs(position) > limit:
                breaches[instrument] = position
        if breaches:
            LOGGER.warning("Position limit breaches detected: %s", breaches)
        return breaches

    def health_summary(self) -> Mapping[str, object]:
        return {
            "reports": len(self._reports),
            "audit_trail": len(self._audit_trail),
            "execution_quality": len(self._execution_quality),
            "synchronised_at": (
                self._synchronised_at.isoformat() if self._synchronised_at else None
            ),
            "market_abuse_signals": len(self._abuse_signals),
        }

    def snapshot(self) -> ComplianceSnapshot:
        return ComplianceSnapshot(
            reports=list(self._reports),
            audit_trail=list(self._audit_trail),
            execution_quality=list(self._execution_quality),
        )

    def export(self, *, prefix: str = "mifid2") -> Path:
        snapshot = self.snapshot()
        payload = {
            "generated_at": snapshot.generated_at.isoformat(),
            "reports": [report.to_dict() for report in snapshot.reports],
            "audit_trail": [entry.to_dict() for entry in snapshot.audit_trail],
            "execution_quality": [
                _slots_to_dict(quality) for quality in snapshot.execution_quality
            ],
            "market_abuse_signals": [
                _slots_to_dict(signal) for signal in self._abuse_signals
            ],
        }
        target = (
            self._storage_path
            / f"{prefix}-{snapshot.generated_at.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        target.write_text(json.dumps(payload, indent=2))
        self._apply_retention()
        return target

    def _apply_retention(self) -> None:
        cutoff = datetime.now(UTC) - self._retention.retention_delta()
        for artefact in list(self._storage_path.glob("*.json")):
            try:
                timestamp = datetime.strptime(
                    artefact.stem.split("-")[-1], "%Y%m%dT%H%M%SZ"
                ).replace(tzinfo=UTC)
            except ValueError:
                continue
            if timestamp < cutoff:
                artefact.unlink(missing_ok=True)

    def _analyse_market_abuse(self, entry: OrderAuditTrail) -> None:
        payload = entry.payload
        raw_size = payload.get("size", 0)
        size = float(raw_size) if isinstance(raw_size, (int, float, str)) else 0.0
        if size <= 0:
            return
        if payload.get("action") == "cancel" and size > 1_000_000:
            self._abuse_signals.append(
                MarketAbuseSignal(
                    order_id=entry.order_id,
                    actor=entry.actor,
                    reason="suspicious large cancellation",
                ),
            )

    def generate_regulatory_report(self) -> Mapping[str, object]:
        return {
            "health": self.health_summary(),
            "best_execution_breaches": [
                _slots_to_dict(quality) for quality in self.best_execution_breaches()
            ],
            "market_abuse_signals": [
                _slots_to_dict(signal) for signal in self._abuse_signals
            ],
        }


__all__ = [
    "ComplianceSnapshot",
    "ExecutionQuality",
    "MarketAbuseSignal",
    "MiFID2Reporter",
    "MiFID2RetentionPolicy",
    "OrderAuditTrail",
    "TransactionReport",
]
