"""HTTP/SSE fallback server for CoherenceBridge."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

if TYPE_CHECKING:
    from coherence_bridge.engine_interface import SignalEngine
    from coherence_bridge.questdb_writer import QuestDBSignalWriter

from coherence_bridge.invariants import verify_signal

app = FastAPI(title="CoherenceBridge", version="1.0.0")

engine: SignalEngine | None = None
writer: QuestDBSignalWriter | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    assert engine is not None
    return {"healthy": True, "instruments": engine.instruments}


@app.get("/metrics")
def prometheus_metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/signal/{instrument}")
def snapshot(instrument: str) -> Any:
    assert engine is not None
    sig = engine.get_signal(instrument)
    if sig is None:
        return JSONResponse(
            {"error": f"Unknown instrument: {instrument}"},
            status_code=404,
        )
    verify_signal(sig, raise_on_failure=False)
    return sig


@app.get("/stream")
async def stream(
    request: Request,
    instruments: str = "",
    interval_ms: int = 1000,
) -> StreamingResponse:
    """SSE endpoint: GET /stream?instruments=EURUSD,GBPUSD&interval_ms=1000"""
    assert engine is not None
    inst_list = [i.strip() for i in instruments.split(",") if i.strip()]
    if not inst_list:
        inst_list = engine.instruments
    interval_s = max(interval_ms, 100) / 1000.0

    async def generate() -> AsyncGenerator[str, None]:
        while True:
            if await request.is_disconnected():
                break
            for inst in inst_list:
                sig = engine.get_signal(inst)
                if sig is not None:
                    yield f"data: {json.dumps(sig)}\n\n"
                    if writer is not None:
                        with contextlib.suppress(Exception):
                            writer.write_signal(sig)
            await asyncio.sleep(interval_s)

    return StreamingResponse(generate(), media_type="text/event-stream")
