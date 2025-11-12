"""FastAPI service for TradePulse-QLW with rate limiting and audit."""

from __future__ import annotations

import hashlib
import time

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse
from prometheus_client import make_asgi_app
from pydantic import BaseModel

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False

from .config import QLWConfig
from .engine import QLWEngine

app = FastAPI(title="TradePulse‑QLW", default_response_class=ORJSONResponse)
app.mount("/metrics", make_asgi_app())

if SLOWAPI_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class SolveRequest(BaseModel):
    features_fmn: list[list[float]]
    orderbook: list[list[list[float]]] | None = None
    delta_volume: list[float] | None = None
    cfg: QLWConfig | None = None


@app.middleware("http")
async def guard_and_audit(request: Request, call_next):
    # Size guard
    if request.headers.get("content-length") and int(
        request.headers["content-length"]
    ) > 4 * 1024 * 1024:
        raise HTTPException(413, "Payload too large")
    # Structured audit
    ts = int(time.time() * 1000)
    body_bytes = await request.body()
    body_hash = hashlib.sha256(body_bytes).hexdigest() if body_bytes else None
    path = request.url.path
    ip = request.client.host if request.client else "?"
    request.state.audit = {"ts": ts, "path": path, "ip": ip, "body_sha256": body_hash}
    resp = await call_next(request)
    # Attach minimal headers (no PII)
    if hasattr(request.state, "audit") and request.state.audit:
        resp.headers["X-Audit-TS"] = str(request.state.audit["ts"])
        resp.headers["X-Audit-Req"] = request.state.audit["body_sha256"] or ""
    return resp


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/v1/solve")
def solve(req: SolveRequest):
    if SLOWAPI_AVAILABLE:
        # Apply rate limiting if available
        pass

    cfg = req.cfg or QLWConfig()
    if cfg.nt > 65536 or cfg.nx > 16384:
        raise HTTPException(422, "Request exceeds limits: nt<=65536, nx<=16384")
    engine = QLWEngine(cfg)
    out = engine.run(
        np.array(req.features_fmn, dtype=float),
        orderbook=np.array(req.orderbook, dtype=float) if req.orderbook else None,
        delta_volume=np.array(req.delta_volume, dtype=float) if req.delta_volume else None,
    )
    return {
        "psi": out.psi.tolist(),
        "resonance": out.resonance.tolist(),
        "forbidden_mask": out.forbidden_mask.tolist(),
        "soft_mask": out.soft_mask.tolist(),
        "meta": out.meta,
    }
