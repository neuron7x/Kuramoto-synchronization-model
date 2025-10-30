"""Utilities that keep numeric libraries deterministic across environments."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import os
from typing import MutableMapping

THREAD_BOUND_ENV_VARS: dict[str, str] = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "ACCELERATE_MAX_THREADS": "1",
}


def apply_thread_determinism(env: MutableMapping[str, str] | None = None) -> None:
    """Ensure thread-bound environment variables default to a single worker."""

    target = env if env is not None else os.environ
    for key, value in THREAD_BOUND_ENV_VARS.items():
        target.setdefault(key, value)


__all__ = ["THREAD_BOUND_ENV_VARS", "apply_thread_determinism"]
