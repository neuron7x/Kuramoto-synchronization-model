"""Mapping utilities between domain objects and DTOs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from domain import ModelMetadata, Order, Position, Signal


def signal_to_dto(signal: Signal) -> dict[str, Any]:
    """Convert a :class:`domain.signal.Signal` into a DTO."""

    return signal.to_dict()


def order_to_dto(order: Order) -> dict[str, Any]:
    """Convert a :class:`domain.order.Order` into primitives."""

    return order.to_dict()


def position_to_dto(position: Position) -> dict[str, Any]:
    """Convert a :class:`domain.position.Position` into primitives."""

    return position.to_dict()


def dto_to_signal(data: Mapping[str, Any]) -> Signal:
    """Instantiate a domain signal from serialized data."""

    raw_ts = data.get("timestamp")
    if isinstance(raw_ts, str):
        timestamp = datetime.fromisoformat(raw_ts)
    elif isinstance(raw_ts, datetime):
        timestamp = raw_ts
    elif raw_ts is None:
        timestamp = datetime.now(timezone.utc)
    else:  # pragma: no cover - defensive branch
        raise TypeError("timestamp must be str, datetime, or None")

    raw_training_ts = data.get("training_timestamp")
    if isinstance(raw_training_ts, str):
        training_ts = datetime.fromisoformat(raw_training_ts)
    elif isinstance(raw_training_ts, datetime):
        training_ts = raw_training_ts
    else:
        raise TypeError("training_timestamp must be an ISO string or datetime")

    try:
        model_metadata = ModelMetadata(
            model_id=str(data["model_id"]),
            model_version=str(data["model_version"]),
            model_hash=str(data["model_hash"]),
            training_timestamp=training_ts,
        )
    except KeyError as exc:  # pragma: no cover - validated by Signal tests
        missing = exc.args[0]
        raise KeyError(f"Signal payload missing required model metadata field: {missing}") from exc

    return Signal(
        symbol=str(data["symbol"]),
        action=data["action"],
        confidence=float(data.get("confidence", 0.0)),
        model_metadata=model_metadata,
        timestamp=timestamp,
        rationale=data.get("rationale"),
        metadata=data.get("metadata"),
    )


__all__ = ["signal_to_dto", "order_to_dto", "position_to_dto", "dto_to_signal"]
