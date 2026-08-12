# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared helpers for deterministic, debuggable property tests.

The utilities centralise Hypothesis configuration so that every property test
is reproducible, uses non-overlapping RNG seeds, and emits rich debugging
artifacts when a counterexample is discovered.  This keeps failures actionable
even in large CI matrices where log volume is constrained.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np
import pandas as pd

try:  # pragma: no cover - Hypothesis is optional in some environments
    from hypothesis import HealthCheck, Phase, note
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Hypothesis must be installed to use property utilities") from exc

_SEED_REGISTRY: dict[str, int] = {}


def _stable_seed(identifier: str) -> int:
    """Return a deterministic 63-bit seed derived from *identifier*."""

    digest = hashlib.sha256(identifier.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
    registered = _SEED_REGISTRY.setdefault(identifier, value)
    if registered != value:
        raise RuntimeError(f"seed collision detected for identifier={identifier!r}")
    return value


def property_settings(identifier: str, *, max_examples: int = 128) -> dict[str, Any]:
    """Return a consistent :func:`hypothesis.settings` payload.

    ``identifier`` is typically the test function name.  The returned mapping can
    be unpacked into ``@settings(**property_settings(...))``.  All tests run with
    deterministic seeds and without the example database to prevent seed reuse
    across shards while still allowing Hypothesis to shrink counterexamples.
    """

    _stable_seed(identifier)
    return {
        "max_examples": max_examples,
        "deadline": None,
        "suppress_health_check": [HealthCheck.too_slow],
        "derandomize": True,
        "phases": (Phase.generate, Phase.target, Phase.shrink),
        "print_blob": True,
        "database": None,
    }


def property_seed(identifier: str) -> int:
    """Return the deterministic seed assigned to ``identifier``."""

    return _stable_seed(identifier)


def _serialise_value(value: Any) -> Any:
    """Convert complex objects into JSON-serialisable forms for debugging."""

    if is_dataclass(value) and not isinstance(value, type):
        return _serialise_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _serialise_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialise_value(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return {
            "shape": list(value.shape),
            "columns": list(map(str, value.columns)),
            "index_start": value.index[0].isoformat() if not value.empty else None,
            "index_end": value.index[-1].isoformat() if not value.empty else None,
        }
    if isinstance(value, pd.Series):
        return {
            "shape": [value.shape[0]],
            "name": str(value.name),
            "index_start": value.index[0].isoformat() if not value.empty else None,
            "index_end": value.index[-1].isoformat() if not value.empty else None,
        }
    if isinstance(value, (np.generic,)):  # numpy scalars
        return value.item()
    if isinstance(value, (np.ndarray,)):
        return {
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "min": float(np.nanmin(value)) if value.size else None,
            "max": float(np.nanmax(value)) if value.size else None,
        }
    if isinstance(value, (float, int, str)) or value is None:
        return value
    return repr(value)


def regression_note(label: str, payload: Mapping[str, Any] | None = None) -> None:
    """Emit a concise JSON snippet describing the current scenario.

    The helper should be invoked inside property tests to aid reproduction of
    failing examples.  The snippets are small enough to survive log redaction in
    CI environments yet contain enough metadata to understand the counterexample
    without re-running shrink steps locally.
    """

    structured = _serialise_value(payload or {})
    note(f"{label}: {json.dumps(structured, sort_keys=True)}")


__all__ = [
    "property_settings",
    "property_seed",
    "regression_note",
]
