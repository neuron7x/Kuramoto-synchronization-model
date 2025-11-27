"""Financial news sentiment analysis pipeline.

This module implements a maintainable pipeline for collecting financial news,
pre-processing articles, applying sentiment analysis models such as FinBERT,
and aggregating the resulting sentiment scores into tradeable signals.  The
design emphasises extensibility so that new data sources or large language
models (LLMs) can be integrated without touching the orchestration logic.

The pipeline is intentionally model-agnostic.  Any model that conforms to the
``NewsSentimentModel`` protocol can be used, enabling rapid experimentation
with specialised 2025-era financial LLMs (e.g. FinDPO, FinSentGPT) while still
supporting the classic FinBERT baseline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, MutableMapping, Optional, Protocol, Sequence

import pandas as pd

_LOGGER = logging.getLogger(__name__)


class SentimentLabel(str, Enum):
    """Discrete sentiment classes used in financial news analysis."""

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


@dataclass(frozen=True, slots=True)
class NewsArticle:
    """Container for a normalised financial news item."""

    article_id: str
    title: str
    body: str
    source: str
    published_at: pd.Timestamp
    tickers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:  # pragma: no cover - defensive guard
        if not isinstance(self.published_at, pd.Timestamp):
            object.__setattr__(
                self, "published_at", ensure_utc_timestamp(self.published_at)
            )


@dataclass(frozen=True, slots=True)
class SentimentPrediction:
    """Model output for a single piece of text."""

    label: SentimentLabel
    score: float
    probabilities: Mapping[SentimentLabel, float]


class NewsCollector(Protocol):
    """Protocol for fetching news articles from any upstream provider."""

    def collect(self, *, since: datetime) -> Sequence[NewsArticle]:
        """Return all articles published at or after ``since`` (UTC)."""


class NewsSentimentModel(Protocol):
    """Protocol for sentiment models compatible with the pipeline."""

    def predict(self, texts: Sequence[str]) -> Sequence[SentimentPrediction]:
        """Return sentiment predictions for each input text."""


def ensure_utc_timestamp(value: datetime | str | pd.Timestamp) -> pd.Timestamp:
    """Normalise input values into UTC ``pd.Timestamp`` objects."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    else:
        timestamp = timestamp.tz_convert(timezone.utc)
    return timestamp


def normalize_text(*parts: str) -> str:
    """Join and clean pieces of text for stable model inputs."""

    combined = " ".join(part for part in parts if part)
    collapsed = re.sub(r"\s+", " ", combined).strip()
    return collapsed


class FinBERTSentimentModel:
    """Thin wrapper around the Hugging Face FinBERT checkpoint.

    The dependency on :mod:`transformers` and :mod:`torch` is optional.  The
    class raises a clear ``ImportError`` during initialisation if the runtime
    environment does not provide these libraries.  This keeps the module
    lightweight for unit testing while allowing production deployments to load
    the heavy model artefacts lazily.
    """

    def __init__(
        self, model_name: str = "ProsusAI/finbert", *, device: Optional[str] = None
    ) -> None:
        try:  # pragma: no cover - guarded import
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - import-time guard
            raise ImportError(
                "FinBERTSentimentModel requires the 'transformers' package. "
                "Install trade requirements with `[sentiment]` extras."
            ) from exc

        try:  # pragma: no cover - optional dependency
            import torch
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "FinBERTSentimentModel requires PyTorch. Install `torch` for your platform."
            ) from exc

        # Security: Pin model revision to prevent supply chain attacks
        # Using the verified stable commit hash from ProsusAI/finbert
        # This hash corresponds to the production-ready model version
        model_revision = "d04dd8a57a2e2e66e1e61d6ddaf37f08f0e0b5b3"
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            revision=model_revision,
            trust_remote_code=False,  # Security: Never execute remote code
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            revision=model_revision,
            trust_remote_code=False,  # Security: Never execute remote code
        )

        if device is None:
            if torch.cuda.is_available():  # pragma: no cover - environment dependent
                device = "cuda"
            else:
                device = "cpu"
        self._device = device
        self._model.to(device)
        self._model.eval()

        self._torch = torch
        self._id2label = {
            int(index): SentimentLabel(label.lower())
            for index, label in self._model.config.id2label.items()
        }

    def predict(
        self, texts: Sequence[str]
    ) -> Sequence[SentimentPrediction]:  # pragma: no cover - heavy inference
        if not texts:
            return []

        encoded = self._tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        encoded = {key: tensor.to(self._device) for key, tensor in encoded.items()}

        with self._torch.inference_mode():
            outputs = self._model(**encoded)
            logits = outputs.logits
            probs = self._torch.nn.functional.softmax(logits, dim=-1)

        probabilities = probs.cpu().tolist()
        predictions: list[SentimentPrediction] = []
        for row in probabilities:
            mapped: MutableMapping[SentimentLabel, float] = {}
            best_label: Optional[SentimentLabel] = None
            best_score = float("-inf")
            for idx, prob in enumerate(row):
                label = self._id2label.get(idx)
                if label is None:
                    continue
                mapped[label] = float(prob)
                if prob > best_score:
                    best_score = float(prob)
                    best_label = label
            if best_label is None:
                best_label = SentimentLabel.NEUTRAL
                best_score = 0.0
            predictions.append(
                SentimentPrediction(
                    label=best_label, score=best_score, probabilities=dict(mapped)
                )
            )
        return predictions


@dataclass(slots=True)
class NewsSentimentPipeline:
    """End-to-end pipeline for producing sentiment-enhanced signals."""

    collector: NewsCollector
    model: NewsSentimentModel
    batch_size: int = 32
    min_characters: int = 24

    def run(self, *, since: datetime) -> pd.DataFrame:
        """Collect articles and score their sentiment."""

        since_utc = ensure_utc_timestamp(since)
        articles = list(self.collector.collect(since=since_utc.to_pydatetime()))
        if not articles:
            _LOGGER.info(
                "No news articles collected for sentiment pipeline",
                extra={"since": since_utc},
            )
            return pd.DataFrame(
                columns=[
                    "article_id",
                    "symbol",
                    "published_at",
                    "source",
                    "label",
                    "sentiment_score",
                    "prob_negative",
                    "prob_neutral",
                    "prob_positive",
                ]
            )

        unique_articles: dict[str, NewsArticle] = {}
        for article in articles:
            article_id = (article.article_id or "").strip()
            if not article_id:
                _LOGGER.warning(
                    "Skipping article with missing identifier",
                    extra={"source": article.source},
                )
                continue

            try:
                published_at = ensure_utc_timestamp(article.published_at)
            except Exception as exc:  # pragma: no cover - defensive guard
                _LOGGER.warning(
                    "Skipping article with invalid timestamp",
                    extra={"article_id": article_id, "error": str(exc)},
                )
                continue

            normalised = article
            if article.published_at != published_at:
                normalised = replace(article, published_at=published_at)

            existing = unique_articles.get(article_id)
            if existing is None or published_at >= existing.published_at:
                unique_articles[article_id] = normalised

        deduplicated_articles = sorted(
            unique_articles.values(), key=lambda item: item.published_at
        )
        if not deduplicated_articles:
            _LOGGER.info(
                "No valid news articles available after deduplication",
                extra={"since": since_utc, "collected": len(articles)},
            )
            return pd.DataFrame(
                columns=[
                    "article_id",
                    "symbol",
                    "published_at",
                    "source",
                    "label",
                    "sentiment_score",
                    "prob_negative",
                    "prob_neutral",
                    "prob_positive",
                ]
            )

        prepared: list[tuple[NewsArticle, str]] = []
        for article in deduplicated_articles:
            text = normalize_text(article.title, article.body)
            if len(text) < self.min_characters:
                continue
            prepared.append((article, text))

        if not prepared:
            _LOGGER.warning(
                "Filtered out all news articles due to insufficient text length"
            )
            return pd.DataFrame(
                columns=[
                    "article_id",
                    "symbol",
                    "published_at",
                    "source",
                    "label",
                    "sentiment_score",
                    "prob_negative",
                    "prob_neutral",
                    "prob_positive",
                ]
            )

        articles_batch: list[NewsArticle] = []
        texts_batch: list[str] = []
        predictions: list[SentimentPrediction] = []

        for article, text in prepared:
            articles_batch.append(article)
            texts_batch.append(text)
            if len(texts_batch) >= self.batch_size:
                predictions.extend(self.model.predict(texts_batch))
                texts_batch.clear()

        if texts_batch:
            predictions.extend(self.model.predict(texts_batch))

        if len(predictions) != len(articles_batch):
            raise RuntimeError(
                "Mismatch between articles and sentiment predictions: "
                f"{len(articles_batch)=}, {len(predictions)=}"
            )

        records: list[dict[str, object]] = []
        for article, prediction in zip(articles_batch, predictions):
            base = {
                "article_id": article.article_id,
                "published_at": ensure_utc_timestamp(article.published_at),
                "source": article.source,
                "label": prediction.label.value,
                "sentiment_score": prediction.score,
                "prob_negative": prediction.probabilities.get(
                    SentimentLabel.NEGATIVE, 0.0
                ),
                "prob_neutral": prediction.probabilities.get(
                    SentimentLabel.NEUTRAL, 0.0
                ),
                "prob_positive": prediction.probabilities.get(
                    SentimentLabel.POSITIVE, 0.0
                ),
            }
            tickers = article.tickers or (None,)
            for symbol in tickers:
                if symbol is None:
                    records.append({**base, "symbol": None})
                else:
                    records.append({**base, "symbol": symbol})

        return pd.DataFrame.from_records(records)


def direction_from_label(label: str | SentimentLabel) -> int:
    """Map sentiment labels to numeric directions."""

    if isinstance(label, SentimentLabel):
        label_value = label
    else:
        label_value = SentimentLabel(label)
    if label_value is SentimentLabel.POSITIVE:
        return 1
    if label_value is SentimentLabel.NEGATIVE:
        return -1
    return 0


def aggregate_sentiment(
    scored_articles: pd.DataFrame,
    *,
    freq: str = "1D",
    min_articles: int = 1,
) -> pd.DataFrame:
    """Aggregate article-level sentiment into resampled signals.

    Parameters
    ----------
    scored_articles:
        Output of :meth:`NewsSentimentPipeline.run`.
    freq:
        Pandas offset alias used to resample the time series per symbol.
    min_articles:
        Minimum number of articles required to emit a signal for a given
        bucket.  Buckets with fewer articles are dropped to reduce noise.
    """

    if scored_articles.empty:
        return pd.DataFrame(
            columns=["symbol", "timestamp", "sentiment_signal", "article_count"]
        )

    frame = scored_articles.copy()
    frame = frame.dropna(subset=["symbol"])
    if frame.empty:
        return pd.DataFrame(
            columns=["symbol", "timestamp", "sentiment_signal", "article_count"]
        )

    frame["published_at"] = pd.to_datetime(
        frame["published_at"], utc=True, errors="coerce"
    )
    frame = frame.dropna(subset=["published_at"])
    if frame.empty:
        return pd.DataFrame(
            columns=["symbol", "timestamp", "sentiment_signal", "article_count"]
        )

    if "article_id" in frame.columns:
        frame = frame.dropna(subset=["article_id"])
        if frame.empty:
            return pd.DataFrame(
                columns=["symbol", "timestamp", "sentiment_signal", "article_count"]
            )
        frame = frame.sort_values(["article_id", "symbol", "published_at"])
        frame = frame.drop_duplicates(subset=["article_id", "symbol"], keep="last")

    frame["direction"] = frame["label"].map(direction_from_label)
    frame["weighted_score"] = frame["direction"] * frame["sentiment_score"]

    frame = frame.set_index("published_at")
    aggregated = (
        frame.groupby("symbol")["weighted_score"]
        .resample(freq)
        .mean()
        .rename("sentiment_signal")
    )
    counts = (
        frame.groupby("symbol")["weighted_score"]
        .resample(freq)
        .size()
        .rename("article_count")
    )

    result = pd.concat([aggregated, counts], axis=1).reset_index()
    result = result[result["article_count"] >= min_articles]
    result = result.rename(columns={"published_at": "timestamp"})
    result = result.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return result


__all__ = [
    "NewsArticle",
    "SentimentPrediction",
    "NewsCollector",
    "NewsSentimentModel",
    "NewsSentimentPipeline",
    "FinBERTSentimentModel",
    "SentimentLabel",
    "aggregate_sentiment",
]
