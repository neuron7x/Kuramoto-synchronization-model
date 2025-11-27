"""Generic event bus abstractions and broker integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class BrokerMessage:
    """Message to be published through a :class:`MessageBroker`."""

    topic: str
    payload: bytes
    headers: Mapping[str, str] | None = None


class MessageBroker(Protocol):
    """Minimal interface implemented by message brokers used in the pipeline."""

    async def start(self) -> None:  # pragma: no cover - protocol definition
        """Open broker connections and allocate resources."""

    async def stop(self) -> None:  # pragma: no cover - protocol definition
        """Release broker resources and close network connections."""

    async def publish(
        self, message: BrokerMessage
    ) -> None:  # pragma: no cover - protocol definition
        """Publish ``message`` to the broker."""


class NullMessageBroker:
    """No-op broker used when event publication is optional."""

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, message: BrokerMessage) -> None:
        return None


class FunctionalMessageBroker:
    """Adapter turning simple callables into a :class:`MessageBroker`."""

    def __init__(
        self,
        *,
        start: Callable[[], Awaitable[None]] | None = None,
        stop: Callable[[], Awaitable[None]] | None = None,
        publish: Callable[[BrokerMessage], Awaitable[None]],
    ) -> None:
        self._start = start or (lambda: _noop_async())
        self._stop = stop or (lambda: _noop_async())
        self._publish = publish

    async def start(self) -> None:
        await self._start()

    async def stop(self) -> None:
        await self._stop()

    async def publish(self, message: BrokerMessage) -> None:
        await self._publish(message)


async def _noop_async() -> None:
    return None


class KafkaMessageBroker:
    """Adapter around ``aiokafka``-compatible producers."""

    def __init__(self, producer: Any) -> None:
        self._producer = producer

    async def start(self) -> None:
        start = getattr(self._producer, "start", None)
        if start is not None:
            await start()

    async def stop(self) -> None:
        stop = getattr(self._producer, "stop", None)
        if stop is not None:
            await stop()

    async def publish(self, message: BrokerMessage) -> None:
        send = getattr(self._producer, "send_and_wait", None)
        if send is None:
            send = getattr(self._producer, "send", None)
        if send is None:
            raise RuntimeError("Kafka producer does not implement send/send_and_wait")
        headers = message.headers or {}
        encoded_headers = tuple(
            (key, value.encode("utf-8")) for key, value in headers.items()
        )
        result = send(message.topic, message.payload, headers=encoded_headers)
        if isinstance(result, Awaitable):
            await result


class RabbitMQMessageBroker:
    """Adapter for ``aio_pika`` based RabbitMQ publishers."""

    def __init__(
        self,
        connection: Any,
        *,
        exchange_name: str,
        routing_key: str | None = None,
        declare_exchange: bool = False,
    ) -> None:
        self._connection = connection
        self._exchange_name = exchange_name
        self._routing_key = routing_key
        self._declare_exchange = declare_exchange
        self._channel: Any | None = None
        self._exchange: Any | None = None

    async def start(self) -> None:
        self._channel = await self._connection.channel()
        declare_kwargs: dict[str, Any] = {"name": self._exchange_name}
        if self._declare_exchange:
            declare_kwargs.update(
                {
                    "type": _resolve_exchange_type(),
                    "durable": True,
                    "auto_delete": False,
                }
            )
        else:
            declare_kwargs["passive"] = True
        self._exchange = await self._channel.declare_exchange(**declare_kwargs)

    async def stop(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._exchange = None

    async def publish(self, message: BrokerMessage) -> None:
        if self._exchange is None:
            raise RuntimeError(
                "RabbitMQMessageBroker.start must be awaited before publishing"
            )
        payload = message.payload
        headers = dict(message.headers or {})
        module = _import_aio_pika()
        amqp_message = module.Message(
            payload, headers=headers, content_type="application/json"
        )
        routing_key = message.topic or self._routing_key
        if routing_key is None:
            raise ValueError(
                "routing_key must be provided when publishing RabbitMQ messages"
            )
        await self._exchange.publish(amqp_message, routing_key=routing_key)


def _import_aio_pika() -> Any:
    import importlib

    return importlib.import_module("aio_pika")


def _resolve_exchange_type() -> Any:
    module = _import_aio_pika()
    return getattr(module, "ExchangeType").TOPIC


__all__ = [
    "BrokerMessage",
    "FunctionalMessageBroker",
    "KafkaMessageBroker",
    "MessageBroker",
    "NullMessageBroker",
    "RabbitMQMessageBroker",
]
