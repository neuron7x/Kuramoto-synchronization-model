"""FastAPI application exposing TradePulse dashboard data and live streams."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from runtime.dashboard_data import build_dashboard_snapshot

app = FastAPI(title="TradePulse Dashboard API", version="1.0.0")


def _build_payload() -> Dict[str, Any]:
    """Return a fresh snapshot to avoid accidental mutation between requests."""

    snapshot = build_dashboard_snapshot()
    return snapshot


@app.get("/dashboard/snapshot")
async def get_snapshot() -> Dict[str, Any]:
    """Return full dashboard payload used for initial hydration."""

    return _build_payload()


@app.get("/dashboard/overview")
async def get_overview() -> Dict[str, Any]:
    return _build_payload()["overview"]


@app.get("/dashboard/monitoring")
async def get_monitoring() -> Dict[str, Any]:
    return _build_payload()["monitoring"]


@app.get("/dashboard/positions")
async def get_positions() -> Dict[str, Any]:
    return _build_payload()["positions"]


@app.get("/dashboard/orders")
async def get_orders() -> Dict[str, Any]:
    return _build_payload()["orders"]


@app.get("/dashboard/pnl")
async def get_pnl() -> Dict[str, Any]:
    return _build_payload()["pnl"]


@app.get("/dashboard/signals")
async def get_signals() -> Dict[str, Any]:
    return _build_payload()["signals"]


@app.get("/dashboard/community")
async def get_community() -> Dict[str, Any]:
    return _build_payload()["community"]


@app.websocket("/dashboard/stream")
async def dashboard_stream(websocket: WebSocket) -> None:
    """Push live updates for dashboard clients via WebSocket."""

    await websocket.accept()
    try:
        # Send initial snapshot to bootstrap newly connected clients.
        snapshot = _build_payload()
        await websocket.send_json({"type": "snapshot", "payload": snapshot})

        while True:
            await asyncio.sleep(3)
            incremental = _build_payload()
            for route in ("orders", "positions", "pnl", "signals", "monitoring"):
                await websocket.send_json({"type": route, "payload": incremental[route]})
    except WebSocketDisconnect:  # pragma: no cover - network interruption is expected
        return


__all__ = ["app"]
