# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kafka connector interface that is explicitly disabled in this package."""

from __future__ import annotations

from typing import AsyncIterator

from .base import BaseIngestor, RawEvent

__all__ = ["KafkaIngestor", "KafkaConnectorUnavailableError"]


class KafkaConnectorUnavailableError(RuntimeError):
    """Raised when Kafka ingestion is requested in the MFN connector package."""


_KAFKA_UNAVAILABLE_MESSAGE = (
    "Kafka ingestion is disabled for mycelium_fractal_net.connectors. "
    "Use source_type='rest' or source_type='file'."
)


class KafkaIngestor(BaseIngestor):
    """Fail-closed connector type kept only for explicit compatibility errors."""

    def __init__(
        self,
        bootstrap_servers: str | list[str],
        topic: str,
        *,
        group_id: str = "mfn-consumer",
        auto_offset_reset: str = "latest",
        batch_size: int = 100,
        source_name: str | None = None,
        security_protocol: str = "PLAINTEXT",
        sasl_mechanism: str | None = None,
        sasl_username: str | None = None,
        sasl_password: str | None = None,
    ) -> None:
        del (
            bootstrap_servers,
            topic,
            group_id,
            auto_offset_reset,
            batch_size,
            source_name,
            security_protocol,
            sasl_mechanism,
            sasl_username,
            sasl_password,
        )
        raise KafkaConnectorUnavailableError(_KAFKA_UNAVAILABLE_MESSAGE)

    async def connect(self) -> None:
        raise KafkaConnectorUnavailableError(_KAFKA_UNAVAILABLE_MESSAGE)

    async def fetch(self) -> AsyncIterator[RawEvent]:
        raise KafkaConnectorUnavailableError(_KAFKA_UNAVAILABLE_MESSAGE)
        yield  # pragma: no cover

    async def close(self) -> None:
        raise KafkaConnectorUnavailableError(_KAFKA_UNAVAILABLE_MESSAGE)
