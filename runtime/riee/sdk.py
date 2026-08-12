from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from runtime.riee.engine import state_interceptor

RIEE_ENABLE_ENV = "RIEE_ENABLE"


def riee_guard(
    claims_path: str = "CLAIMS.md",
    threshold: float = 1e-6,
) -> Callable[[Callable[..., float]], Callable[..., float]]:
    """Application-SDK entrypoint for runtime guarding.

    Enabled when `RIEE_ENABLE=1`; otherwise returns passthrough decorator.
    """

    def passthrough(fn: Callable[..., float]) -> Callable[..., float]:
        return fn

    if os.getenv(RIEE_ENABLE_ENV, "0") != "1":
        return passthrough
    return state_interceptor(Path(claims_path), threshold=threshold)
