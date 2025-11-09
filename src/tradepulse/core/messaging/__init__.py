"""Messaging primitives for TradePulse event streaming."""

from .contracts import SchemaContractError, SchemaContractValidator
from .event_bus import (
    EventBusConfig,
    EventEnvelope,
    EventTopic,
    KafkaEventBus,
    NATSEventBus,
)
from .idempotency import EventIdempotencyStore, InMemoryEventIdempotencyStore
from .schema_registry import (
    EventSchemaRegistry,
    SchemaCompatibilityError,
    SchemaFormat,
    SchemaFormatCoverageError,
    SchemaLintError,
)

__all__ = [
    "EventBusConfig",
    "EventEnvelope",
    "EventTopic",
    "KafkaEventBus",
    "NATSEventBus",
    "EventSchemaRegistry",
    "SchemaFormat",
    "SchemaCompatibilityError",
    "SchemaFormatCoverageError",
    "SchemaLintError",
    "SchemaContractValidator",
    "SchemaContractError",
    "EventIdempotencyStore",
    "InMemoryEventIdempotencyStore",
]
