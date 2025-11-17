"""Streaming sentiment integration for social media data sources.

This module provides lightweight primitives for consuming alternative data
feeds such as Twitter or Reddit in real time, transforming raw social posts
into :class:`~core.altdata.sentiment.SentimentSignal` instances and aggregating
them into features that can be ingested by forecasting models.  The goal is to
capture collective mood swings ahead of market moves by maintaining a rolling
window of weighted sentiment observations.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable, Mapping, Sequence

import pandas as pd

from .sentiment import SentimentFeatureBuilder, SentimentSignal

_TOKEN_PATTERN = re.compile(r"[A-Za-z]+")
_CASHTAG_PATTERN = re.compile(r"\$([A-Z]{1,6})(?=\b)")

_DEFAULT_POSITIVE = {
    "moon",
    "pump",
    "bull",
    "win",
    "gain",
    "green",
    "rocket",
    "strong",
    "breakout",
}

_DEFAULT_NEGATIVE = {
    "dump",
    "bear",
    "loss",
    "red",
    "down",
    "panic",
    "fear",
    "rug",
}

_EMOJI_SENTIMENT = {
    "🚀": 1.0,
    "🔥": 0.6,
    "💎": 0.8,
    "🤑": 0.9,
    "✅": 0.5,
    "😡": -0.7,
    "😱": -0.9,
    "💩": -1.0,
    "❌": -0.6,
}


@dataclass(slots=True)
class SocialPost:
    """Canonical representation of a single social media post."""

    timestamp: datetime
    platform: str
    text: str
    author: str | None = None
    symbols: Sequence[str] | None = None
    language: str | None = None
    engagement: Mapping[str, float] | None = None
    metadata: Mapping[str, object] | None = None


@dataclass(slots=True)
class SocialListeningConfig:
    """Configuration governing social sentiment aggregation."""

    window: timedelta = timedelta(minutes=30)
    frequency: str = "1min"
    publish_interval: timedelta = timedelta(minutes=1)
    snapshot_interval: timedelta = timedelta(minutes=1)

    def __post_init__(self) -> None:
        if self.window <= timedelta(0):
            raise ValueError("window must be greater than zero")
        if not self.frequency or not self.frequency.strip():
            raise ValueError("frequency must be a non-empty string")
        if self.publish_interval < timedelta(0):
            raise ValueError("publish_interval must be non-negative")
        if self.snapshot_interval < timedelta(0):
            raise ValueError("snapshot_interval must be non-negative")


class SocialSentimentScorer:
    """Approximate sentiment of short-form social media messages."""

    def __init__(
        self,
        *,
        positive_tokens: Sequence[str] | None = None,
        negative_tokens: Sequence[str] | None = None,
        emoji_weights: Mapping[str, float] | None = None,
        emphasis_multiplier: float = 1.4,
    ) -> None:
        self._positive = {
            token.lower() for token in (positive_tokens or _DEFAULT_POSITIVE)
        }
        self._negative = {
            token.lower() for token in (negative_tokens or _DEFAULT_NEGATIVE)
        }
        self._emoji = dict(emoji_weights or _EMOJI_SENTIMENT)
        self._emphasis_multiplier = max(1.0, emphasis_multiplier)

    def _tokenise(self, text: str) -> list[str]:
        return [match.group(0).lower() for match in _TOKEN_PATTERN.finditer(text or "")]

    def score(self, text: str) -> float:
        """Return a bounded sentiment score in ``[-1, 1]`` for ``text``."""

        tokens = self._tokenise(text)
        positive = negative = 0.0
        for token in tokens:
            weight = self._emphasis_multiplier if token.isupper() else 1.0
            if token in self._positive:
                positive += weight
            elif token in self._negative:
                negative += weight
        emoji_delta = 0.0
        for char in text or "":
            emoji_delta += self._emoji.get(char, 0.0)
        base = positive - negative + emoji_delta
        total = positive + negative + abs(emoji_delta)
        if total == 0:
            return 0.0
        score = base / max(total, 1.0)
        return float(max(-1.0, min(1.0, score)))

    def extract_symbols(self, text: str) -> list[str]:
        """Return unique upper-case cashtags referenced in ``text``."""

        return sorted(
            {match.group(1) for match in _CASHTAG_PATTERN.finditer(text or "")}
        )


class SocialSignalFactory:
    """Convert :class:`SocialPost` objects into sentiment-weighted signals."""

    def __init__(
        self,
        scorer: SocialSentimentScorer | None = None,
        *,
        base_volume: float = 1.0,
        engagement_weight: float = 0.35,
    ) -> None:
        self._scorer = scorer or SocialSentimentScorer()
        self._base_volume = max(0.0, float(base_volume))
        self._engagement_weight = max(0.0, float(engagement_weight))

    def _normalise_timestamp(self, timestamp: datetime) -> datetime:
        ts = timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        else:
            ts = ts.astimezone(UTC)
        return ts

    def _resolve_symbols(self, post: SocialPost) -> Sequence[str]:
        if post.symbols:
            return tuple({symbol.upper() for symbol in post.symbols if symbol})
        extracted = self._scorer.extract_symbols(post.text)
        return extracted or ("GLOBAL",)

    def _engagement_volume(self, post: SocialPost) -> float:
        engagement = post.engagement or {}
        if not engagement:
            return self._base_volume
        total = 0.0
        for value in engagement.values():
            try:
                total += max(0.0, float(value))
            except (TypeError, ValueError):
                continue
        weighted = self._base_volume + self._engagement_weight * math.log1p(total)
        return float(max(self._base_volume, weighted))

    def from_post(self, post: SocialPost) -> list[SentimentSignal]:
        """Return one or more :class:`SentimentSignal` derived from ``post``."""

        timestamp = self._normalise_timestamp(post.timestamp)
        score = self._scorer.score(post.text)
        volume = self._engagement_volume(post)
        platform = post.platform.lower().strip() or "unknown"
        signals: list[SentimentSignal] = []
        for symbol in self._resolve_symbols(post):
            metadata: dict[str, object] = {
                "author": post.author or "anonymous",
                "symbol": symbol,
                "language": post.language or "und",
            }
            if post.metadata:
                metadata.update(post.metadata)
            signals.append(
                SentimentSignal(
                    timestamp=timestamp,
                    source=platform,
                    score=score,
                    volume=volume,
                    metadata=metadata,
                )
            )
        return signals


class _SignalBuffer:
    """Maintain a rolling window of :class:`SentimentSignal` instances."""

    def __init__(self, *, window: timedelta) -> None:
        self._window = window
        self._signals: deque[SentimentSignal] = deque()

    def append(self, signal: SentimentSignal) -> None:
        self._signals.append(signal)
        self._evict(signal.timestamp)

    def extend(self, signals: Iterable[SentimentSignal]) -> None:
        for signal in signals:
            self.append(signal)

    def _evict(self, current_timestamp: datetime) -> None:
        cutoff = current_timestamp - self._window
        while self._signals and self._signals[0].timestamp < cutoff:
            self._signals.popleft()

    def __iter__(self):  # pragma: no cover - exercised indirectly
        return iter(self._signals)

    def __len__(self) -> int:  # pragma: no cover - convenience only
        return len(self._signals)

    def as_list(self) -> list[SentimentSignal]:
        return list(self._signals)

    def grouped_by_symbol(self) -> dict[str, list[SentimentSignal]]:
        grouped: dict[str, list[SentimentSignal]] = defaultdict(list)
        for signal in self._signals:
            metadata = signal.metadata or {}
            symbol = str(metadata.get("symbol", "GLOBAL")).upper()
            grouped[symbol].append(signal)
        return grouped

    @property
    def latest_timestamp(self) -> datetime | None:
        if not self._signals:
            return None
        return self._signals[-1].timestamp


class SocialListeningProcessor:
    """Orchestrate scoring, buffering and feature aggregation for posts."""

    def __init__(
        self,
        *,
        config: SocialListeningConfig | None = None,
        signal_factory: SocialSignalFactory | None = None,
        feature_builder: SentimentFeatureBuilder | None = None,
    ) -> None:
        self._config = config or SocialListeningConfig()
        self._buffer = _SignalBuffer(window=self._config.window)
        self._factory = signal_factory or SocialSignalFactory()
        self._feature_builder = feature_builder or SentimentFeatureBuilder()

    @property
    def config(self) -> SocialListeningConfig:
        return self._config

    def ingest(self, posts: SocialPost | Iterable[SocialPost]) -> list[SentimentSignal]:
        """Score ``posts`` and append the resulting signals to the buffer."""

        if isinstance(posts, SocialPost):
            posts_iterable = [posts]
        else:
            posts_iterable = list(posts)
        signals: list[SentimentSignal] = []
        for post in posts_iterable:
            derived = self._factory.from_post(post)
            self._buffer.extend(derived)
            signals.extend(derived)
        return signals

    def aggregate(self) -> pd.DataFrame:
        """Return resampled sentiment features per symbol."""

        grouped = {
            symbol: signals
            for symbol, signals in self._buffer.grouped_by_symbol().items()
            if signals
        }
        aggregated: dict[str, pd.DataFrame] = {}
        for symbol, signals in grouped.items():
            frame = self._feature_builder.aggregate(
                signals, freq=self._config.frequency
            )
            if not frame.empty:
                aggregated[symbol] = frame
        if not aggregated:
            empty_index = pd.MultiIndex(
                levels=[[], []],
                codes=[[], []],
                names=["symbol", "timestamp"],
            )
            return pd.DataFrame(
                columns=["sentiment_vwap", "sentiment_momentum", "sources"],
                index=empty_index,
            )
        return pd.concat(aggregated, names=["symbol", "timestamp"]).sort_index()

    def snapshot(self) -> dict[str, dict[str, float]]:
        """Return the latest sentiment snapshot keyed by symbol."""

        grouped = self._buffer.grouped_by_symbol()
        snapshots: dict[str, dict[str, float]] = {}
        for symbol, signals in grouped.items():
            if not signals:
                continue
            snapshots[symbol] = self._feature_builder.latest(signals)
        return snapshots

    @property
    def latest_timestamp(self) -> datetime | None:
        """Expose the timestamp of the newest ingested signal."""

        return self._buffer.latest_timestamp


__all__ = [
    "SocialListeningConfig",
    "SocialListeningProcessor",
    "SocialPost",
    "SocialSentimentScorer",
    "SocialSignalFactory",
]
