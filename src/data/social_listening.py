# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Streaming pipeline for social media sentiment ingestion."""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import AsyncIterator, Callable, Mapping, Protocol, Sequence

import pandas as pd

from core.altdata.social_listening import (
    SocialListeningConfig,
    SocialListeningProcessor,
    SocialPost,
)

from .event_bus import BrokerMessage, MessageBroker, NullMessageBroker


class SocialStreamClient(Protocol):
    """Protocol implemented by social media streaming adapters."""

    async def start(self) -> None:  # pragma: no cover - protocol definition
        """Allocate network resources before streaming begins."""

    async def stop(self) -> None:  # pragma: no cover - protocol definition
        """Release resources previously allocated in :meth:`start`."""

    def stream(
        self,
    ) -> AsyncIterator[SocialPost]:  # pragma: no cover - protocol definition
        """Yield :class:`SocialPost` instances as they are observed."""


@dataclass(slots=True)
class SocialPublicationConfig:
    """Control publication behaviour of :class:`SocialListeningPipeline`."""

    features_topic: str = "geosync.altdata.social.features"
    snapshot_topic: str = "geosync.altdata.social.snapshots"
    content_type: str = "application/json"


class SocialListeningPipeline:
    """Consume social media streams and publish aggregated sentiment."""

    def __init__(
        self,
        *,
        clients: Sequence[SocialStreamClient],
        processor: SocialListeningProcessor | None = None,
        message_broker: MessageBroker | None = None,
        config: SocialListeningConfig | None = None,
        publication: SocialPublicationConfig | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        frame_encoder: Callable[[pd.DataFrame], bytes] | None = None,
        snapshot_encoder: (
            Callable[[Mapping[str, dict[str, float]]], bytes] | None
        ) = None,
    ) -> None:
        self._clients = list(clients)
        self._processor = processor or SocialListeningProcessor(config=config)
        self._broker = message_broker or NullMessageBroker()
        self._publication = publication or SocialPublicationConfig()
        self._loop = loop
        self._frame_encoder = frame_encoder or self._default_frame_encoder
        self._snapshot_encoder = snapshot_encoder or self._default_snapshot_encoder
        self._last_features_ts: datetime | None = None
        self._last_snapshot_ts: datetime | None = None

    @property
    def config(self) -> SocialListeningConfig:
        return self._processor.config

    async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Start streaming and block until ``stop_event`` is set or clients finish."""

        external_stop = stop_event or asyncio.Event()
        loop = self._loop or asyncio.get_running_loop()
        await self._broker.start()
        try:
            for client in self._clients:
                await _maybe_call(client, "start")
            tasks = [
                loop.create_task(self._consume(client, external_stop))
                for client in self._clients
            ]
            if not tasks:
                await external_stop.wait()
                return
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
        finally:
            for client in self._clients:
                await _maybe_call(client, "stop")
            await self._broker.stop()

    async def _consume(
        self, client: SocialStreamClient, stop_event: asyncio.Event
    ) -> None:
        stream = client.stream()
        try:
            async for post in stream:
                signals = self._processor.ingest(post)
                if not signals:
                    if stop_event.is_set():
                        break
                    continue
                timestamp = signals[-1].timestamp
                await self._publish_if_due(timestamp)
                if stop_event.is_set():
                    break
        finally:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()

    async def _publish_if_due(self, timestamp: datetime) -> None:
        config = self.config
        if self._is_due(timestamp, self._last_features_ts, config.publish_interval):
            frame = self._processor.aggregate()
            if not frame.empty:
                await self._publish_frame(frame, timestamp)
                self._last_features_ts = timestamp
        if self._is_due(timestamp, self._last_snapshot_ts, config.snapshot_interval):
            snapshot = self._processor.snapshot()
            if snapshot:
                await self._publish_snapshot(snapshot, timestamp)
                self._last_snapshot_ts = timestamp

    async def _publish_frame(self, frame: pd.DataFrame, timestamp: datetime) -> None:
        payload = self._frame_encoder(frame)
        message = BrokerMessage(
            topic=self._publication.features_topic,
            payload=payload,
            headers=self._build_headers(timestamp),
        )
        await self._broker.publish(message)

    async def _publish_snapshot(
        self, snapshot: Mapping[str, dict[str, float]], timestamp: datetime
    ) -> None:
        payload = self._snapshot_encoder(snapshot)
        message = BrokerMessage(
            topic=self._publication.snapshot_topic,
            payload=payload,
            headers=self._build_headers(timestamp),
        )
        await self._broker.publish(message)

    def _build_headers(self, timestamp: datetime) -> Mapping[str, str]:
        ts = timestamp.astimezone(UTC).isoformat()
        return {
            "content-type": self._publication.content_type,
            "produced-at": ts,
        }

    @staticmethod
    def _is_due(
        timestamp: datetime,
        last: datetime | None,
        interval: float | int | timedelta | pd.Timedelta | None,
    ) -> bool:
        if interval is None:
            return False
        if isinstance(interval, (int, float)):
            interval_seconds = float(interval)
            if interval_seconds <= 0:
                return True
            delta = (timestamp - (last or timestamp)).total_seconds()
            return last is None or delta >= interval_seconds
        if isinstance(interval, timedelta):
            if interval <= timedelta(0):
                return True
            if last is None:
                return True
            return (timestamp - last) >= interval
        if isinstance(interval, pd.Timedelta):
            seconds = interval.total_seconds()
            if seconds <= 0:
                return True
            if last is None:
                return True
            return (timestamp - last).total_seconds() >= seconds
        raise TypeError("interval must be numeric or timedelta-like")

    @staticmethod
    def _default_frame_encoder(frame: pd.DataFrame) -> bytes:
        if frame.empty:
            return b"[]"
        reset = frame.reset_index()
        records = []
        for row in reset.to_dict(orient="records"):
            ts = pd.Timestamp(row["timestamp"])
            if ts.tzinfo is None:
                ts = ts.tz_localize(UTC)
            else:
                ts = ts.tz_convert(UTC)
            row["timestamp"] = ts.isoformat()
            row["sentiment_vwap"] = float(row["sentiment_vwap"])
            row["sentiment_momentum"] = float(row["sentiment_momentum"])
            row["sources"] = int(row["sources"])
            records.append(row)
        return json.dumps(records, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _default_snapshot_encoder(snapshot: Mapping[str, dict[str, float]]) -> bytes:
        if not snapshot:
            return b"{}"
        normalised: dict[str, dict[str, float]] = {}
        for symbol, metrics in snapshot.items():
            normalised[symbol] = {key: float(value) for key, value in metrics.items()}
        return json.dumps(normalised, separators=(",", ":")).encode("utf-8")


async def _maybe_call(obj: object, method: str) -> None:
    func = getattr(obj, method, None)
    if func is None:
        return
    result = func()
    if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
        await result


__all__ = [
    "SocialListeningPipeline",
    "SocialPublicationConfig",
    "SocialStreamClient",
]
