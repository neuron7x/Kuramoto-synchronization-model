# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Messaging primitives for GeoSync event streaming."""

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
