# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest

from core.altdata.social_listening import (
    SocialListeningConfig,
    SocialListeningProcessor,
    SocialPost,
    SocialSentimentScorer,
    SocialSignalFactory,
)
from core.compat import UTC
from src.data.event_bus import BrokerMessage, MessageBroker
from src.data.social_listening import (
    SocialListeningPipeline,
    SocialPublicationConfig,
)


def _ts(minutes: int) -> datetime:
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    return base + timedelta(minutes=minutes)


def test_social_sentiment_scorer_balances_tokens() -> None:
    scorer = SocialSentimentScorer()
    positive = scorer.score("BTC is going to the moon 🚀🔥")
    negative = scorer.score("This is a rug pull 😡😱")
    assert positive > 0
    assert negative < 0
    neutral = scorer.score("Just observing the market today")
    assert abs(neutral) < 0.2


def test_social_signal_factory_engagement_weighting() -> None:
    scorer = SocialSentimentScorer()
    factory = SocialSignalFactory(scorer, base_volume=1.0, engagement_weight=0.5)
    low = SocialPost(timestamp=_ts(0), platform="twitter", text="meh", engagement={})
    high = SocialPost(
        timestamp=_ts(0),
        platform="twitter",
        text="wow",
        engagement={"likes": 400, "retweets": 50},
    )
    low_volume = factory.from_post(low)[0].volume
    high_volume = factory.from_post(high)[0].volume
    assert high_volume > low_volume


def test_social_listening_processor_grouped_aggregation() -> None:
    config = SocialListeningConfig(window=timedelta(minutes=15), frequency="1min")
    processor = SocialListeningProcessor(config=config)
    posts = [
        SocialPost(timestamp=_ts(0), platform="twitter", text="BTC 🚀", symbols=["BTC"]),
        SocialPost(timestamp=_ts(1), platform="reddit", text="BTC 🚀", symbols=["BTC"]),
        SocialPost(timestamp=_ts(2), platform="twitter", text="ETH 😡", symbols=["ETH"]),
    ]
    processor.ingest(posts)
    aggregated = processor.aggregate()
    assert not aggregated.empty
    assert set(aggregated.index.get_level_values("symbol")) == {"BTC", "ETH"}
    snapshots = processor.snapshot()
    assert snapshots.keys() == {"BTC", "ETH"}


class _FakeBroker(MessageBroker):
    def __init__(self) -> None:
        self.messages: list[BrokerMessage] = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:  # pragma: no cover - trivial
        self.started = True

    async def stop(self) -> None:  # pragma: no cover - trivial
        self.stopped = True

    async def publish(self, message: BrokerMessage) -> None:
        self.messages.append(message)


class _FakeClient:
    def __init__(self, posts: list[SocialPost]) -> None:
        self._posts = posts
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def stream(self):
        async def _iterator():
            for post in self._posts:
                await asyncio.sleep(0)
                yield post

        return _iterator()


@pytest.mark.asyncio
async def test_social_listening_pipeline_publishes_payloads() -> None:
    posts = [
        SocialPost(
            timestamp=_ts(0),
            platform="twitter",
            text="BTC is on fire 🚀",
            symbols=["BTC"],
            engagement={"likes": 100},
        ),
        SocialPost(
            timestamp=_ts(1),
            platform="reddit",
            text="ETH holders are nervous 😡",
            symbols=["ETH"],
            engagement={"upvotes": 40},
        ),
        SocialPost(
            timestamp=_ts(2),
            platform="twitter",
            text="BTC rally continues 🚀🚀",
            symbols=["BTC"],
            engagement={"likes": 50},
        ),
    ]
    client = _FakeClient(posts)
    broker = _FakeBroker()
    config = SocialListeningConfig(
        window=timedelta(minutes=30),
        frequency="1min",
        publish_interval=timedelta(minutes=1),
        snapshot_interval=timedelta(minutes=1),
    )
    processor = SocialListeningProcessor(config=config)
    publication = SocialPublicationConfig(features_topic="features", snapshot_topic="snapshots")
    pipeline = SocialListeningPipeline(
        clients=[client],
        processor=processor,
        message_broker=broker,
        publication=publication,
    )
    await pipeline.run()

    assert broker.started and broker.stopped
    feature_messages = [m for m in broker.messages if m.topic == "features"]
    snapshot_messages = [m for m in broker.messages if m.topic == "snapshots"]
    assert feature_messages and snapshot_messages

    features_payload = json.loads(feature_messages[-1].payload.decode("utf-8"))
    assert any(record["symbol"] == "BTC" for record in features_payload)
    assert any("sentiment_vwap" in record for record in features_payload)

    snapshots_payload = json.loads(snapshot_messages[-1].payload.decode("utf-8"))
    assert {"BTC", "ETH"}.issubset(snapshots_payload.keys())
