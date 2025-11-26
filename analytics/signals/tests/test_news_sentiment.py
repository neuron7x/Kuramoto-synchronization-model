from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from analytics.signals.news_sentiment import (
    NewsArticle,
    NewsSentimentPipeline,
    SentimentLabel,
    aggregate_sentiment,
)


class DummyCollector:
    def __init__(self, articles: list[NewsArticle]) -> None:
        self._articles = articles

    def collect(self, *, since: datetime) -> list[NewsArticle]:
        since_ts = pd.Timestamp(since)
        if since_ts.tzinfo is None:
            since_ts = since_ts.tz_localize("UTC")
        else:
            since_ts = since_ts.tz_convert("UTC")
        return [
            article for article in self._articles if article.published_at >= since_ts
        ]


class DummyModel:
    def predict(self, texts: list[str]) -> list:
        predictions = []
        for text in texts:
            if "loss" in text.lower():
                probabilities = {
                    SentimentLabel.NEGATIVE: 0.8,
                    SentimentLabel.NEUTRAL: 0.15,
                    SentimentLabel.POSITIVE: 0.05,
                }
                predictions.append(
                    DummyPrediction(
                        label=SentimentLabel.NEGATIVE,
                        score=0.8,
                        probabilities=probabilities,
                    )
                )
            else:
                probabilities = {
                    SentimentLabel.NEGATIVE: 0.05,
                    SentimentLabel.NEUTRAL: 0.1,
                    SentimentLabel.POSITIVE: 0.85,
                }
                predictions.append(
                    DummyPrediction(
                        label=SentimentLabel.POSITIVE,
                        score=0.85,
                        probabilities=probabilities,
                    )
                )
        return predictions


class DummyPrediction:
    def __init__(
        self,
        *,
        label: SentimentLabel,
        score: float,
        probabilities: dict[SentimentLabel, float],
    ) -> None:
        self.label = label
        self.score = score
        self.probabilities = probabilities


def test_pipeline_scores_articles() -> None:
    articles = [
        NewsArticle(
            article_id="a-1",
            title="Company beats expectations",
            body="Earnings soar for the quarter",
            source="Reuters",
            published_at=pd.Timestamp("2025-10-01T12:00:00Z"),
            tickers=("AAPL",),
        ),
        NewsArticle(
            article_id="a-2",
            title="Company issues profit warning",
            body="Loss expected amid supply chain issues",
            source="Bloomberg",
            published_at=pd.Timestamp("2025-10-01T14:30:00Z"),
            tickers=("AAPL", "MSFT"),
        ),
    ]

    pipeline = NewsSentimentPipeline(
        collector=DummyCollector(articles), model=DummyModel(), batch_size=8
    )
    scored = pipeline.run(since=datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc))

    assert not scored.empty
    assert set(scored.columns) == {
        "article_id",
        "symbol",
        "published_at",
        "source",
        "label",
        "sentiment_score",
        "prob_negative",
        "prob_neutral",
        "prob_positive",
    }
    assert len(scored) == 3  # a-1 for AAPL, a-2 for AAPL and MSFT
    assert (scored[scored["article_id"] == "a-2"]["symbol"].tolist()) == [
        "AAPL",
        "MSFT",
    ]


def test_aggregate_sentiment_daily_mean() -> None:
    scored = pd.DataFrame(
        [
            {
                "article_id": "a-1",
                "symbol": "AAPL",
                "published_at": pd.Timestamp("2025-10-01T12:00:00Z"),
                "source": "Reuters",
                "label": "positive",
                "sentiment_score": 0.9,
                "prob_negative": 0.05,
                "prob_neutral": 0.05,
                "prob_positive": 0.9,
            },
            {
                "article_id": "a-2",
                "symbol": "AAPL",
                "published_at": pd.Timestamp("2025-10-01T16:00:00Z"),
                "source": "Bloomberg",
                "label": "negative",
                "sentiment_score": 0.8,
                "prob_negative": 0.8,
                "prob_neutral": 0.15,
                "prob_positive": 0.05,
            },
            {
                "article_id": "a-3",
                "symbol": "MSFT",
                "published_at": pd.Timestamp("2025-10-01T13:00:00Z"),
                "source": "FT",
                "label": "positive",
                "sentiment_score": 0.7,
                "prob_negative": 0.1,
                "prob_neutral": 0.2,
                "prob_positive": 0.7,
            },
        ]
    )

    aggregated = aggregate_sentiment(scored, freq="1D", min_articles=1)

    assert set(aggregated.columns) == {
        "symbol",
        "timestamp",
        "sentiment_signal",
        "article_count",
    }
    assert len(aggregated) == 2

    apple_row = aggregated[aggregated["symbol"] == "AAPL"].iloc[0]
    expected = (0.9 - 0.8) / 2
    assert apple_row["sentiment_signal"] == pytest.approx(expected)
    assert apple_row["article_count"] == 2


def test_aggregate_sentiment_minimum_articles_filter() -> None:
    scored = pd.DataFrame(
        [
            {
                "article_id": "a-1",
                "symbol": "AAPL",
                "published_at": pd.Timestamp("2025-10-02T09:00:00Z"),
                "source": "Reuters",
                "label": "positive",
                "sentiment_score": 0.6,
                "prob_negative": 0.1,
                "prob_neutral": 0.3,
                "prob_positive": 0.6,
            }
        ]
    )

    aggregated = aggregate_sentiment(scored, freq="1D", min_articles=2)

    assert aggregated.empty


def test_pipeline_deduplicates_articles_by_identifier() -> None:
    base_time = pd.Timestamp("2025-10-03T10:00:00Z")
    articles = [
        NewsArticle(
            article_id="dup-1",
            title="Company outlook improves",
            body="Revenue expected to climb",
            source="Reuters",
            published_at=base_time,
            tickers=("AAPL",),
        ),
        NewsArticle(
            article_id="dup-1",
            title="Company warns about losses",
            body="Loss anticipated due to recall",
            source="Reuters",
            published_at=base_time + pd.Timedelta(minutes=5),
            tickers=("AAPL",),
        ),
    ]

    pipeline = NewsSentimentPipeline(
        collector=DummyCollector(articles), model=DummyModel(), batch_size=4
    )
    scored = pipeline.run(since=datetime(2025, 10, 3, 9, 0, tzinfo=timezone.utc))

    assert len(scored) == 1
    row = scored.iloc[0]
    assert row["article_id"] == "dup-1"
    assert row["label"] == SentimentLabel.NEGATIVE.value
    assert row["sentiment_score"] == pytest.approx(0.8)


def test_aggregate_sentiment_deduplicates_duplicate_articles() -> None:
    scored = pd.DataFrame(
        [
            {
                "article_id": "dup-1",
                "symbol": "AAPL",
                "published_at": pd.Timestamp("2025-10-04T10:00:00Z"),
                "source": "Reuters",
                "label": "positive",
                "sentiment_score": 0.6,
                "prob_negative": 0.1,
                "prob_neutral": 0.3,
                "prob_positive": 0.6,
            },
            {
                "article_id": "dup-1",
                "symbol": "AAPL",
                "published_at": pd.Timestamp("2025-10-04T10:10:00Z"),
                "source": "Reuters",
                "label": "negative",
                "sentiment_score": 0.4,
                "prob_negative": 0.7,
                "prob_neutral": 0.2,
                "prob_positive": 0.1,
            },
            {
                "article_id": "unique-1",
                "symbol": "AAPL",
                "published_at": pd.Timestamp("2025-10-04T12:00:00Z"),
                "source": "Bloomberg",
                "label": "positive",
                "sentiment_score": 0.5,
                "prob_negative": 0.2,
                "prob_neutral": 0.2,
                "prob_positive": 0.6,
            },
        ]
    )

    aggregated = aggregate_sentiment(scored, freq="1D", min_articles=1)

    assert len(aggregated) == 1
    row = aggregated.iloc[0]
    expected_signal = (-0.4 + 0.5) / 2
    assert row["sentiment_signal"] == pytest.approx(expected_signal)
    assert row["article_count"] == 2
