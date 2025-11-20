"""Utilities for capturing immutable pre-session state snapshots."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from execution.connectors import ExecutionConnector
from execution.risk import RiskLimits, RiskManager

__all__ = [
    "ExecutionMode",
    "SessionSnapshotError",
    "SessionSnapshotter",
]


class ExecutionMode(str, Enum):
    """Enumerate supported execution modes for session lifecycle snapshots."""

    LIVE = "live"
    PAPER = "paper"
    SHADOW = "shadow"


class SessionSnapshotError(RuntimeError):
    """Raised when a session snapshot cannot be captured or validated."""


@dataclass(slots=True)
class _VenueSnapshot:
    name: str
    balance: dict[str, object]
    positions: Sequence[dict[str, object]]
    issues: Sequence[str]


class SessionSnapshotter:
    """Capture and persist immutable session state snapshots for auditing."""

    def __init__(
        self,
        directory: Path | str,
        *,
        mode: ExecutionMode,
        risk_manager: RiskManager,
    ) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._mode = ExecutionMode(mode)
        self._risk_manager = risk_manager

    # ------------------------------------------------------------------
    def capture(
        self,
        connectors: Mapping[str, ExecutionConnector],
        *,
        preloaded: (
            Mapping[str, tuple[Sequence[Mapping[str, object]], Sequence[str]]] | None
        ) = None,
    ) -> Path:
        """Persist an immutable snapshot for the provided *connectors*."""

        timestamp = datetime.now(timezone.utc)
        venues: list[_VenueSnapshot] = []
        for name in sorted(connectors):
            cached = preloaded.get(name) if preloaded is not None else None
            venues.append(self._build_venue_snapshot(name, connectors[name], cached))

        payload = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "mode": self._mode.value,
            "venues": [
                {
                    "name": venue.name,
                    "balance": venue.balance,
                    "positions": venue.positions,
                    "issues": list(venue.issues),
                }
                for venue in venues
            ],
            "risk_limits": self._serialise_risk_limits(self._risk_manager.limits),
            "risk_exposure": self._serialise_exposure(),
            "kill_switch": self._serialise_kill_switch(),
        }

        return self._persist(payload, timestamp)

    # ------------------------------------------------------------------
    def _build_venue_snapshot(
        self,
        name: str,
        connector: ExecutionConnector,
        preloaded: tuple[Sequence[Mapping[str, object]], Sequence[str]] | None,
    ) -> _VenueSnapshot:
        positions_iter: Iterable[Mapping[str, object]] = []
        issues: list[str] = []

        if preloaded is not None:
            cached_positions, cached_issues = preloaded
            positions_iter = [
                payload for payload in cached_positions if isinstance(payload, Mapping)
            ]
            issues.extend(str(item) for item in cached_issues if item)
        else:
            get_positions = getattr(connector, "get_positions", None)
            if callable(get_positions):
                try:
                    raw_positions = get_positions()
                except Exception as exc:
                    issues.append(
                        f"positions_unavailable:{type(exc).__name__}:{exc}".rstrip(":")
                    )
                    raw_positions = []
                positions_iter = [
                    payload for payload in raw_positions if isinstance(payload, Mapping)
                ]
            else:
                issues.append("positions_unsupported")

        positions: list[dict[str, object]] = []
        asset_balances: dict[str, float] = {}
        estimated_equity = 0.0

        for payload in positions_iter:
            parsed = self._parse_position(payload)
            if parsed is None:
                continue
            symbol, net_qty, avg_price, notional = parsed
            asset_balances[symbol] = round(
                asset_balances.get(symbol, 0.0) + net_qty, 12
            )
            estimated_equity += abs(notional)
            record: dict[str, object] = {
                "symbol": symbol,
                "net_quantity": round(net_qty, 12),
                "notional": round(notional, 12),
            }
            if avg_price is not None:
                record["average_price"] = round(avg_price, 12)
            positions.append(record)

        positions.sort(key=lambda item: item["symbol"])

        balance_payload: dict[str, object] = {
            "assets": asset_balances,
            "estimated_equity": round(estimated_equity, 12),
        }

        return _VenueSnapshot(
            name=name,
            balance=balance_payload,
            positions=positions,
            issues=tuple(sorted(set(issues))),
        )

    @staticmethod
    def _parse_position(
        payload: Mapping[str, object],
    ) -> tuple[str, float, float | None, float] | None:
        symbol = str(
            payload.get("symbol")
            or payload.get("instrument")
            or payload.get("asset")
            or ""
        ).strip()
        if not symbol:
            return None

        def _first(keys: Sequence[str]) -> float | None:
            for key in keys:
                if key not in payload:
                    continue
                try:
                    value = float(payload[key])
                except (TypeError, ValueError):
                    continue
                return value
            return None

        net_qty = _first(
            [
                "net_quantity",
                "net_qty",
                "net_position",
                "quantity",
                "qty",
            ]
        )
        if net_qty is None:
            long_qty = _first(["long_quantity", "long_qty"])
            short_qty = _first(["short_quantity", "short_qty"])
            if long_qty is None and short_qty is None:
                return None
            net_qty = (long_qty or 0.0) - (short_qty or 0.0)

        avg_price = _first(
            [
                "mark_price",
                "average_price",
                "avg_price",
                "price",
                "mid_price",
            ]
        )
        if avg_price is None:
            if net_qty > 0:
                avg_price = _first(["long_average_price", "long_avg_price"])
            elif net_qty < 0:
                avg_price = _first(["short_average_price", "short_avg_price"])

        notional = 0.0
        if avg_price is not None and abs(net_qty) > 0:
            notional = abs(net_qty) * max(avg_price, 0.0)

        return symbol, float(net_qty), avg_price, float(notional)

    # ------------------------------------------------------------------
    def _serialise_risk_limits(self, limits: RiskLimits) -> dict[str, object]:
        return {
            "max_notional": self._normalise_number(limits.max_notional),
            "max_position": self._normalise_number(limits.max_position),
            "max_orders_per_interval": int(limits.max_orders_per_interval),
            "interval_seconds": self._normalise_number(limits.interval_seconds),
            "kill_switch_limit_multiplier": self._normalise_number(
                limits.kill_switch_limit_multiplier
            ),
            "kill_switch_violation_threshold": int(
                limits.kill_switch_violation_threshold
            ),
            "kill_switch_rate_limit_threshold": int(
                limits.kill_switch_rate_limit_threshold
            ),
        }

    def _serialise_exposure(self) -> dict[str, dict[str, float]]:
        snapshot = self._risk_manager.exposure_snapshot()
        serialised: dict[str, dict[str, float]] = {}
        for symbol, payload in snapshot.items():
            position = 0.0
            notional = 0.0
            if isinstance(payload, Mapping):
                try:
                    position = float(payload.get("position", 0.0))
                except (TypeError, ValueError):
                    position = 0.0
                try:
                    notional = float(payload.get("notional", 0.0))
                except (TypeError, ValueError):
                    notional = 0.0
            serialised[symbol] = {
                "position": round(position, 12),
                "notional": round(notional, 12),
            }
        return dict(sorted(serialised.items()))

    def _serialise_kill_switch(self) -> dict[str, object]:
        kill_switch = self._risk_manager.kill_switch
        limits = self._risk_manager.limits
        return {
            "engaged": bool(kill_switch.is_triggered()),
            "reason": kill_switch.reason,
            "violation_threshold": int(limits.kill_switch_violation_threshold),
            "rate_limit_threshold": int(limits.kill_switch_rate_limit_threshold),
            "limit_multiplier": self._normalise_number(
                limits.kill_switch_limit_multiplier
            ),
        }

    @staticmethod
    def _normalise_number(value: float) -> float | str:
        if isinstance(value, (int, float)):
            if math.isnan(value):  # pragma: no cover - defensive guard
                return "nan"
            if math.isinf(value):
                return "inf" if value > 0 else "-inf"
            return float(value)
        return float(value)

    # ------------------------------------------------------------------
    def _persist(self, payload: dict[str, object], timestamp: datetime) -> Path:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        filename = f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_{self._mode.value}_{digest[:12]}.json"
        destination = self._directory / filename
        if destination.exists():  # pragma: no cover - extremely unlikely
            raise SessionSnapshotError(
                f"snapshot file already exists: {destination.name}"
            )

        record = dict(payload)
        record["hash"] = digest
        destination.write_text(
            json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

        stored = json.loads(destination.read_text(encoding="utf-8"))
        stored_hash = stored.get("hash")
        recalculated = hashlib.sha256(
            json.dumps(
                {k: v for k, v in stored.items() if k != "hash"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if stored_hash != recalculated:
            raise SessionSnapshotError("persisted snapshot failed validation")
        return destination
