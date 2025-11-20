"""Utilities for streaming market data and trading signals."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Any, Deque

from fastapi import WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

LOGGER = logging.getLogger("tradepulse.api.realtime")


class RealTimeStreamManager:
    """Manage live WebSocket connections and broadcast JSON events."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)
        stale: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(payload)
            except WebSocketDisconnect:
                stale.append(connection)
            except Exception:  # pragma: no cover - defensive
                LOGGER.exception("Failed to push realtime update", exc_info=True)
                stale.append(connection)
        if stale:
            async with self._lock:
                for connection in stale:
                    self._connections.discard(connection)

    async def close_all(self, *, code: int = status.WS_1012_SERVICE_RESTART) -> None:
        """Close every active WebSocket connection with a restart signal."""

        async with self._lock:
            connections = list(self._connections)
            self._connections.clear()

        for connection in connections:
            try:
                await connection.close(code=code)
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug(
                    "Failed to close realtime websocket connection", exc_info=True
                )


class AnalyticsStore:
    """Thread-safe in-memory store tracking recent features and predictions."""

    def __init__(self, history_limit: int = 256) -> None:
        self._lock = asyncio.Lock()
        self._feature_history: Deque[BaseModel] = deque(maxlen=history_limit)
        self._prediction_history: Deque[BaseModel] = deque(maxlen=history_limit)
        self._features_by_symbol: dict[str, BaseModel] = {}
        self._predictions_by_symbol: dict[str, BaseModel] = {}

    async def record_feature(self, payload: BaseModel) -> dict[str, Any]:
        entry = payload.model_copy(deep=True)
        symbol = getattr(entry, "symbol", "")
        async with self._lock:
            self._feature_history.appendleft(entry)
            if symbol:
                self._features_by_symbol[symbol] = entry
        return {
            "type": "feature",
            "symbol": symbol,
            "generated_at": _iso(getattr(entry, "generated_at", None)),
            "features": getattr(entry, "features", {}),
            "items": [
                {
                    "timestamp": _iso(getattr(item, "timestamp", None)),
                    "features": getattr(item, "features", {}),
                }
                for item in getattr(entry, "items", [])
            ],
        }

    async def record_prediction(self, payload: BaseModel) -> dict[str, Any]:
        entry = payload.model_copy(deep=True)
        symbol = getattr(entry, "symbol", "")
        async with self._lock:
            self._prediction_history.appendleft(entry)
            if symbol:
                self._predictions_by_symbol[symbol] = entry
        return {
            "type": "signal",
            "symbol": symbol,
            "generated_at": _iso(getattr(entry, "generated_at", None)),
            "horizon_seconds": getattr(entry, "horizon_seconds", None),
            "score": getattr(entry, "score", None),
            "signal": getattr(entry, "signal", {}),
            "items": [
                {
                    "timestamp": _iso(getattr(item, "timestamp", None)),
                    "score": getattr(item, "score", None),
                    "signal": getattr(item, "signal", {}),
                }
                for item in getattr(entry, "items", [])
            ],
        }

    async def snapshot(self, *, limit: int = 25) -> dict[str, Any]:
        async with self._lock:
            features = list(self._feature_history)[:limit]
            predictions = list(self._prediction_history)[:limit]
        return {
            "type": "snapshot",
            "features": [entry.model_dump(mode="json") for entry in features],
            "signals": [entry.model_dump(mode="json") for entry in predictions],
        }

    async def latest_feature(self, symbol: str) -> BaseModel | None:
        async with self._lock:
            entry = self._features_by_symbol.get(symbol)
            return entry.model_copy(deep=True) if entry is not None else None

    async def latest_prediction(self, symbol: str) -> BaseModel | None:
        async with self._lock:
            entry = self._predictions_by_symbol.get(symbol)
            return entry.model_copy(deep=True) if entry is not None else None

    async def recent_features(self, *, limit: int = 20) -> list[BaseModel]:
        async with self._lock:
            return [
                entry.model_copy(deep=True)
                for entry in list(self._feature_history)[:limit]
            ]

    async def recent_predictions(self, *, limit: int = 20) -> list[BaseModel]:
        async with self._lock:
            return [
                entry.model_copy(deep=True)
                for entry in list(self._prediction_history)[:limit]
            ]


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()  # type: ignore[no-any-return]
        except Exception:  # pragma: no cover - defensive
            return None
    return None


__all__ = ["AnalyticsStore", "RealTimeStreamManager"]
