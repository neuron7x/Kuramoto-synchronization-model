from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.data.event_bus import (
    BrokerMessage,
    FunctionalMessageBroker,
    KafkaMessageBroker,
    NullMessageBroker,
    RabbitMQMessageBroker,
)


@pytest.mark.asyncio
async def test_null_message_broker_is_noop() -> None:
    broker = NullMessageBroker()
    message = BrokerMessage(topic="test", payload=b"payload")

    assert await broker.start() is None
    assert await broker.publish(message) is None
    assert await broker.stop() is None


@pytest.mark.asyncio
async def test_functional_message_broker_invokes_callables() -> None:
    start = AsyncMock()
    stop = AsyncMock()
    publish = AsyncMock()
    broker = FunctionalMessageBroker(start=start, stop=stop, publish=publish)
    message = BrokerMessage(topic="orders", payload=b"42", headers={"k": "v"})

    await broker.start()
    await broker.publish(message)
    await broker.stop()

    start.assert_awaited_once()
    stop.assert_awaited_once()
    publish.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_kafka_message_broker_lifecycle_and_publish_awaitable() -> None:
    producer = MagicMock()
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    producer.send_and_wait = AsyncMock(return_value=None)

    broker = KafkaMessageBroker(producer)
    message = BrokerMessage(
        topic="metrics",
        payload=b"{}",
        headers={"x-trace": "abc"},
    )

    await broker.start()
    await broker.publish(message)
    await broker.stop()

    producer.start.assert_awaited_once()
    producer.stop.assert_awaited_once()
    producer.send_and_wait.assert_awaited_once()
    args, kwargs = producer.send_and_wait.await_args
    assert args == ("metrics", b"{}")
    assert kwargs["headers"] == (("x-trace", b"abc"),)


@pytest.mark.asyncio
async def test_kafka_message_broker_falls_back_to_send() -> None:
    class _Producer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, bytes, tuple[tuple[str, bytes], ...]]] = []

        async def send(
            self, topic: str, payload: bytes, *, headers: tuple[tuple[str, bytes], ...]
        ) -> None:
            self.calls.append((topic, payload, headers))

    producer = _Producer()
    broker = KafkaMessageBroker(producer)
    message = BrokerMessage(topic="ticks", payload=b"1", headers={"id": "7"})

    result = await broker.publish(message)

    assert result is None
    assert producer.calls == [("ticks", b"1", (("id", b"7"),))]


@pytest.mark.asyncio
async def test_kafka_message_broker_requires_send_interface() -> None:
    broker = KafkaMessageBroker(object())

    with pytest.raises(RuntimeError, match="does not implement send"):
        await broker.publish(BrokerMessage(topic="noop", payload=b""))


class _FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[Any, str]] = []

    async def publish(self, message: Any, *, routing_key: str) -> None:
        self.published.append((message, routing_key))


class _FakeChannel:
    def __init__(self) -> None:
        self.declare_kwargs: dict[str, Any] | None = None
        self.closed = False
        self.exchange = _FakeExchange()

    async def declare_exchange(self, **kwargs: Any) -> _FakeExchange:
        self.declare_kwargs = kwargs
        return self.exchange

    async def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def __init__(self) -> None:
        self.channel_instance = _FakeChannel()

    async def channel(self) -> _FakeChannel:
        return self.channel_instance


class _FakeMessage:
    def __init__(
        self, payload: bytes, headers: dict[str, str], content_type: str
    ) -> None:
        self.payload = payload
        self.headers = headers
        self.content_type = content_type


class _FakeExchangeType:
    TOPIC = "topic"


@pytest.mark.asyncio
async def test_rabbitmq_message_broker_declares_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = SimpleNamespace(
        Message=_FakeMessage,
        ExchangeType=SimpleNamespace(TOPIC=_FakeExchangeType.TOPIC),
    )
    monkeypatch.setattr("src.data.event_bus._import_aio_pika", lambda: module)

    connection = _FakeConnection()
    broker = RabbitMQMessageBroker(
        connection,
        exchange_name="events",
        routing_key="fallback",
        declare_exchange=True,
    )

    await broker.start()

    channel = connection.channel_instance
    assert channel.declare_kwargs == {
        "name": "events",
        "type": _FakeExchangeType.TOPIC,
        "durable": True,
        "auto_delete": False,
    }

    message = BrokerMessage(topic="", payload=b"payload", headers={"h": "v"})
    await broker.publish(message)

    published_message, routing_key = channel.exchange.published[-1]
    assert published_message.payload == b"payload"
    assert published_message.headers == {"h": "v"}
    assert published_message.content_type == "application/json"
    assert routing_key == "fallback"

    await broker.stop()
    assert channel.closed is True


@pytest.mark.asyncio
async def test_rabbitmq_message_broker_passive_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = SimpleNamespace(
        Message=_FakeMessage,
        ExchangeType=SimpleNamespace(TOPIC=_FakeExchangeType.TOPIC),
    )
    monkeypatch.setattr("src.data.event_bus._import_aio_pika", lambda: module)

    connection = _FakeConnection()
    broker = RabbitMQMessageBroker(
        connection,
        exchange_name="audit",
        routing_key=None,
        declare_exchange=False,
    )

    await broker.start()

    channel = connection.channel_instance
    assert channel.declare_kwargs == {"name": "audit", "passive": True}

    with pytest.raises(ValueError, match="routing_key must be provided"):
        await broker.publish(BrokerMessage(topic="", payload=b""))


@pytest.mark.asyncio
async def test_rabbitmq_message_broker_requires_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = SimpleNamespace(
        Message=_FakeMessage,
        ExchangeType=SimpleNamespace(TOPIC=_FakeExchangeType.TOPIC),
    )
    monkeypatch.setattr("src.data.event_bus._import_aio_pika", lambda: module)

    broker = RabbitMQMessageBroker(
        _FakeConnection(),
        exchange_name="events",
        routing_key="route",
        declare_exchange=False,
    )

    with pytest.raises(RuntimeError, match="must be awaited before publishing"):
        await broker.publish(BrokerMessage(topic="events", payload=b"data"))
