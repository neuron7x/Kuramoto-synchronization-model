"""Event bus abstractions with Kafka backend support."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Dict, MutableMapping, Optional

from .idempotency import (
    EventIdempotencyStore,
    InMemoryEventIdempotencyStore,
    current_timestamp,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopicMetadata:
    name: str
    partition_key: str
    retry_topic: str
    dlq_topic: str


class EventTopic(Enum):
    """Canonical event bus topics."""

    MARKET_TICKS = TopicMetadata(
        name="tradepulse.market.ticks",
        partition_key="symbol",
        retry_topic="tradepulse.market.ticks.retry",
        dlq_topic="tradepulse.market.ticks.dlq",
    )
    MARKET_BARS = TopicMetadata(
        name="tradepulse.market.bars",
        partition_key="symbol",
        retry_topic="tradepulse.market.bars.retry",
        dlq_topic="tradepulse.market.bars.dlq",
    )
    SIGNALS = TopicMetadata(
        name="tradepulse.signals.generated",
        partition_key="symbol",
        retry_topic="tradepulse.signals.generated.retry",
        dlq_topic="tradepulse.signals.generated.dlq",
    )
    ORDERS = TopicMetadata(
        name="tradepulse.execution.orders",
        partition_key="symbol",
        retry_topic="tradepulse.execution.orders.retry",
        dlq_topic="tradepulse.execution.orders.dlq",
    )
    FILLS = TopicMetadata(
        name="tradepulse.execution.fills",
        partition_key="symbol",
        retry_topic="tradepulse.execution.fills.retry",
        dlq_topic="tradepulse.execution.fills.dlq",
    )

    def __str__(self) -> str:
        return self.value.name

    @property
    def metadata(self) -> TopicMetadata:
        return self.value


@dataclass
class EventEnvelope:
    """Transport-agnostic wrapper for payloads."""

    event_type: str
    partition_key: str
    event_id: str
    payload: bytes
    content_type: str
    schema_version: str
    occurred_at: datetime = field(default_factory=current_timestamp)
    headers: MutableMapping[str, str] = field(default_factory=dict)

    def as_message(self) -> Dict[str, str]:
        base: Dict[str, str] = {
            "event_type": self.event_type,
            "partition_key": self.partition_key,
            "event_id": self.event_id,
            "schema_version": str(self.schema_version),
            "occurred_at": self.occurred_at.isoformat(),
            "content_type": self.content_type,
        }
        for key, value in self.headers.items():
            base[key] = value
        return base


class EventBusBackend(str, Enum):
    KAFKA = "kafka"
    NATS = "nats"


@dataclass
class EventBusConfig:
    backend: EventBusBackend
    bootstrap_servers: Optional[str] = None
    nats_url: Optional[str] = None
    client_id: str = "tradepulse-event-bus"
    consumer_group: str = "tradepulse"
    enable_idempotence: bool = True
    retry_attempts: int = 5
    retry_backoff_ms: int = 250
    security_protocol: str = "SSL"
    ssl_cafile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    sasl_mechanism: Optional[str] = "PLAIN"
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None


class BaseEventBus:
    def __init__(
        self,
        config: EventBusConfig,
        idempotency_store: EventIdempotencyStore | None = None,
    ) -> None:
        self._config = config
        self._idempotency = idempotency_store or InMemoryEventIdempotencyStore()

    async def publish(self, topic: EventTopic, envelope: EventEnvelope) -> None:
        raise NotImplementedError

    async def subscribe(
        self,
        topic: EventTopic,
        handler: Callable[[EventEnvelope], Awaitable[None]],
        *,
        durable_name: str | None = None,
    ) -> None:
        raise NotImplementedError

    @property
    def idempotency_store(self) -> EventIdempotencyStore:
        return self._idempotency


class KafkaEventBus(BaseEventBus):
    """Kafka-backed asynchronous event bus."""

    def __init__(
        self,
        config: EventBusConfig,
        idempotency_store: EventIdempotencyStore | None = None,
    ) -> None:
        if config.backend is not EventBusBackend.KAFKA:
            raise ValueError("KafkaEventBus requires a Kafka backend configuration")
        super().__init__(config, idempotency_store=idempotency_store)
        self._producer = None
        self._consumer_tasks: Dict[str, asyncio.Task[None]] = {}
        self._security_kwargs: Dict[str, object] | None = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer

        if not self._config.bootstrap_servers:
            raise ValueError("bootstrap_servers must be configured for Kafka backend")
        security_kwargs = self._get_security_kwargs()
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._config.bootstrap_servers,
            client_id=self._config.client_id,
            enable_idempotence=self._config.enable_idempotence,
            acks="all",
            retry_backoff_ms=self._config.retry_backoff_ms,
            linger_ms=5,
            **security_kwargs,
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
        for task in self._consumer_tasks.values():
            task.cancel()
        self._consumer_tasks.clear()

    async def publish(self, topic: EventTopic, envelope: EventEnvelope) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaEventBus.start() must be called before publish()")
        key = envelope.partition_key.encode("utf-8")
        headers = [
            (name, value.encode("utf-8"))
            for name, value in envelope.as_message().items()
        ]
        await self._producer.send_and_wait(
            topic.metadata.name, envelope.payload, key=key, headers=headers
        )

    async def subscribe(
        self,
        topic: EventTopic,
        handler: Callable[[EventEnvelope], Awaitable[None]],
        *,
        durable_name: str | None = None,
    ) -> None:
        from aiokafka import AIOKafkaConsumer

        group_id = durable_name or self._config.consumer_group
        security_kwargs = self._get_security_kwargs()
        consumer = AIOKafkaConsumer(
            topic.metadata.name,
            bootstrap_servers=self._config.bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            **security_kwargs,
        )
        await consumer.start()

        async def _consume() -> None:
            try:
                async for msg in consumer:
                    envelope = _envelope_from_kafka_message(msg)
                    if self.idempotency_store.was_processed(envelope.event_id):
                        await consumer.commit()
                        continue
                    try:
                        await handler(envelope)
                        self.idempotency_store.mark_processed(envelope.event_id)
                        await consumer.commit()
                    except Exception:
                        await self._publish_retry_or_dlq(topic, envelope)
                        await consumer.commit()
            finally:
                await consumer.stop()

        task = asyncio.create_task(
            _consume(), name=f"kafka-consumer-{topic.metadata.name}"
        )
        self._consumer_tasks[topic.metadata.name] = task

    def _get_security_kwargs(self) -> Dict[str, object]:
        if self._security_kwargs is None:
            self._security_kwargs = self._build_security_kwargs()
        return dict(self._security_kwargs)

    def _build_security_kwargs(self) -> Dict[str, object]:
        protocol = (self._config.security_protocol or "").upper()
        if protocol not in {"SSL", "SASL_SSL"}:
            raise ValueError(
                "Kafka security_protocol must be 'SSL' or 'SASL_SSL' to enforce encrypted transport"
            )

        cafile = self._config.ssl_cafile
        if not cafile:
            raise ValueError(
                "ssl_cafile must be configured for secure Kafka connections"
            )
        cafile_path = Path(cafile)
        if not cafile_path.is_file():
            raise FileNotFoundError(f"ssl_cafile not found at {cafile}")

        certfile = self._config.ssl_certfile
        keyfile = self._config.ssl_keyfile
        if (certfile and not keyfile) or (keyfile and not certfile):
            raise ValueError(
                "ssl_certfile and ssl_keyfile must be provided together when using mutual TLS"
            )

        for name, file_path in {
            "ssl_certfile": certfile,
            "ssl_keyfile": keyfile,
        }.items():
            if file_path is None:
                continue
            path = Path(file_path)
            if not path.is_file():
                raise FileNotFoundError(f"{name} not found at {file_path}")

        ssl_context = ssl.create_default_context(cafile=cafile)
        if certfile and keyfile:
            ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)

        kwargs: Dict[str, object] = {
            "security_protocol": protocol,
            "ssl_context": ssl_context,
        }

        if protocol == "SASL_SSL":
            if not self._config.sasl_username or not self._config.sasl_password:
                raise ValueError(
                    "SASL credentials must be supplied for SASL_SSL protocol"
                )
            mechanism = self._config.sasl_mechanism or "PLAIN"
            kwargs.update(
                {
                    "sasl_mechanism": mechanism,
                    "sasl_plain_username": self._config.sasl_username,
                    "sasl_plain_password": self._config.sasl_password,
                }
            )

        return kwargs

    async def _publish_retry_or_dlq(
        self, topic: EventTopic, envelope: EventEnvelope
    ) -> None:
        if self._producer is None:
            return
        attempt = int(envelope.headers.get("retry-attempt", "0")) + 1
        if attempt <= self._config.retry_attempts:
            envelope.headers["retry-attempt"] = str(attempt)
            await self._producer.send_and_wait(
                topic.metadata.retry_topic,
                envelope.payload,
                key=envelope.partition_key.encode("utf-8"),
                headers=[
                    (k, v.encode("utf-8")) for k, v in envelope.as_message().items()
                ],
            )
        else:
            await self._producer.send_and_wait(
                topic.metadata.dlq_topic,
                envelope.payload,
                key=envelope.partition_key.encode("utf-8"),
                headers=[
                    (k, v.encode("utf-8")) for k, v in envelope.as_message().items()
                ],
            )


class NATSEventBus(BaseEventBus):
    """NATS JetStream backed event bus."""

    def __init__(
        self,
        config: EventBusConfig,
        idempotency_store: EventIdempotencyStore | None = None,
    ) -> None:
        if config.backend is not EventBusBackend.NATS:
            raise ValueError("NATSEventBus requires a NATS backend configuration")
        super().__init__(config, idempotency_store=idempotency_store)
        self._nc = None
        self._js = None
        self._streams_initialised: Dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        import nats

        self._nc = await nats.connect(
            self._config.nats_url or "nats://127.0.0.1:4222",
            name=self._config.client_id,
        )
        self._js = self._nc.jetstream()

    async def stop(self) -> None:
        if self._nc:
            await self._nc.drain()
            await self._nc.close()

    async def publish(self, topic: EventTopic, envelope: EventEnvelope) -> None:
        if not self._nc or not self._js:
            raise RuntimeError("NATSEventBus.start() must be called before publish()")
        await self._ensure_stream(topic)
        headers = {k: v for k, v in envelope.as_message().items()}
        await self._js.publish(
            subject=topic.metadata.name,
            payload=envelope.payload,
            headers=headers,
            timeout=5,
        )

    async def subscribe(
        self,
        topic: EventTopic,
        handler: Callable[[EventEnvelope], Awaitable[None]],
        *,
        durable_name: str | None = None,
    ) -> None:
        if not self._nc or not self._js:
            raise RuntimeError("NATSEventBus.start() must be called before subscribe()")
        await self._ensure_stream(topic)

        async def _callback(msg) -> None:
            envelope = _envelope_from_nats_message(msg)
            if self.idempotency_store.was_processed(envelope.event_id):
                await msg.ack()
                return
            try:
                await handler(envelope)
                self.idempotency_store.mark_processed(envelope.event_id)
                await msg.ack()
            except Exception:
                await self._publish_retry_or_dlq(topic, envelope)
                await msg.ack()

        await self._js.subscribe(
            topic.metadata.name,
            durable=durable_name or self._config.consumer_group,
            cb=_callback,
            manual_ack=True,
            idle_heartbeat=5,
        )

    async def _ensure_stream(self, topic: EventTopic) -> None:
        if not self._nc or not self._js:
            raise RuntimeError("NATS client not initialised")
        lock = self._streams_initialised.setdefault(topic.metadata.name, asyncio.Lock())
        async with lock:
            try:
                await self._js.add_stream(
                    name=topic.metadata.name.replace(".", "_"),
                    subjects=[
                        topic.metadata.name,
                        topic.metadata.retry_topic,
                        topic.metadata.dlq_topic,
                    ],
                )
            except Exception as exc:
                # Stream likely already exists; not an error
                _LOGGER.debug(
                    "Stream %s may already exist or add_stream failed: %s",
                    topic.metadata.name,
                    exc,
                )

    async def _publish_retry_or_dlq(
        self, topic: EventTopic, envelope: EventEnvelope
    ) -> None:
        if not self._nc or not self._js:
            return
        attempt = int(envelope.headers.get("retry-attempt", "0")) + 1
        headers = envelope.as_message()
        headers["retry-attempt"] = str(attempt)
        if attempt <= self._config.retry_attempts:
            await self._js.publish(
                topic.metadata.retry_topic, payload=envelope.payload, headers=headers
            )
        else:
            await self._js.publish(
                topic.metadata.dlq_topic, payload=envelope.payload, headers=headers
            )


def _envelope_from_kafka_message(message) -> EventEnvelope:  # type: ignore[no-untyped-def]
    headers = {key: value.decode("utf-8") for key, value in message.headers}
    occurred_at = (
        datetime.fromisoformat(headers.get("occurred_at"))
        if "occurred_at" in headers
        else datetime.now(timezone.utc)
    )
    return EventEnvelope(
        event_type=headers.get("event_type", ""),
        partition_key=headers.get("partition_key", message.key.decode("utf-8")),
        event_id=headers.get("event_id", ""),
        payload=message.value,
        content_type=headers.get("content_type", "application/octet-stream"),
        schema_version=headers.get("schema_version", "0.0.0"),
        occurred_at=occurred_at,
        headers=headers,
    )


def _envelope_from_nats_message(message) -> EventEnvelope:  # type: ignore[no-untyped-def]
    headers = dict(message.headers or {})
    occurred_at_raw = headers.get("occurred_at")
    occurred_at = (
        datetime.fromisoformat(occurred_at_raw)
        if isinstance(occurred_at_raw, str)
        else datetime.now(timezone.utc)
    )
    return EventEnvelope(
        event_type=headers.get("event_type", ""),
        partition_key=headers.get("partition_key", ""),
        event_id=headers.get("event_id", ""),
        payload=bytes(message.data),
        content_type=headers.get("content_type", "application/octet-stream"),
        schema_version=headers.get("schema_version", "0.0.0"),
        occurred_at=occurred_at,
        headers={
            k: (v if isinstance(v, str) else json.dumps(v)) for k, v in headers.items()
        },
    )
