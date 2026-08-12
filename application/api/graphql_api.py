# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GraphQL schema exposing analytics insights for GeoSync."""

from __future__ import annotations

import warnings
from datetime import datetime
from typing import Any, List, Optional

import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.scalars import JSON

from application.api.realtime import AnalyticsStore

# Suppress deprecation noise from transitive dependency rename in strawberry.fastapi.
warnings.filterwarnings(
    "ignore",
    message="The 'lia' package has been renamed to 'cross_web'.",
    category=DeprecationWarning,
)


@strawberry.type
class FeatureSnapshotType:
    timestamp: datetime
    features: JSON


@strawberry.type
class FeatureAnalytics:
    symbol: str
    generated_at: datetime
    features: JSON
    snapshots: List[FeatureSnapshotType]


@strawberry.type
class PredictionSnapshotType:
    timestamp: datetime
    score: float
    signal: JSON


@strawberry.type
class PredictionAnalytics:
    symbol: str
    generated_at: datetime
    horizon_seconds: int
    score: Optional[float]
    signal: JSON
    snapshots: List[PredictionSnapshotType]


def _feature_to_graphql(model: Any) -> FeatureAnalytics:
    items = [
        FeatureSnapshotType(timestamp=item.timestamp, features=item.features)
        for item in getattr(model, "items", [])
    ]
    return FeatureAnalytics(
        symbol=getattr(model, "symbol"),
        generated_at=getattr(model, "generated_at"),
        features=getattr(model, "features", {}),
        snapshots=items,
    )


def _prediction_to_graphql(model: Any) -> PredictionAnalytics:
    items = [
        PredictionSnapshotType(
            timestamp=item.timestamp,
            score=getattr(item, "score", 0.0),
            signal=getattr(item, "signal", {}),
        )
        for item in getattr(model, "items", [])
    ]
    return PredictionAnalytics(
        symbol=getattr(model, "symbol"),
        generated_at=getattr(model, "generated_at"),
        horizon_seconds=getattr(model, "horizon_seconds", 0),
        score=getattr(model, "score", None),
        signal=getattr(model, "signal", {}),
        snapshots=items,
    )


def create_graphql_router(store: AnalyticsStore) -> GraphQLRouter:
    """Build a FastAPI-compatible GraphQL router bound to the analytics store."""

    @strawberry.type
    class Query:
        @strawberry.field(description="Latest engineered feature vector for the symbol")
        async def latest_feature(self, symbol: str) -> Optional[FeatureAnalytics]:
            feature = await store.latest_feature(symbol)
            if feature is None:
                return None
            return _feature_to_graphql(feature)

        @strawberry.field(description="Recent feature vectors ordered by recency")
        async def recent_features(self, limit: int = 20) -> List[FeatureAnalytics]:
            records = await store.recent_features(limit=limit)
            return [_feature_to_graphql(item) for item in records]

        @strawberry.field(description="Latest generated trading signal for the symbol")
        async def latest_signal(self, symbol: str) -> Optional[PredictionAnalytics]:
            signal = await store.latest_prediction(symbol)
            if signal is None:
                return None
            return _prediction_to_graphql(signal)

        @strawberry.field(description="Recent trading signals ordered by recency")
        async def recent_signals(self, limit: int = 20) -> List[PredictionAnalytics]:
            records = await store.recent_predictions(limit=limit)
            return [_prediction_to_graphql(item) for item in records]

    schema = strawberry.Schema(query=Query)
    return GraphQLRouter(schema, graphql_ide="graphiql")


__all__ = ["create_graphql_router"]
