"""Legacy package shim.

Canonical code lives under ``tradepulse`` (src/tradepulse). This package remains
for backward compatibility and forwards duplicated neuro modules to the
canonical implementations. Legacy-only modules (e.g., core.utils) continue to
reside here.
"""

from __future__ import annotations

import sys
from importlib import import_module


def __getattr__(name: str):
    """Forward known duplicate symbols to the canonical tradepulse.core."""

    try:
        return getattr(import_module("tradepulse.core"), name)
    except Exception as exc:
        raise AttributeError(name) from exc


# Explicit aliasing for serotonin controllers to ensure object identity across
# legacy and canonical import paths.
try:  # pragma: no cover - best effort mapping
    _sero_mod = import_module("tradepulse.core.neuro.serotonin.serotonin_controller")
    sys.modules["core.neuro.serotonin"] = import_module("tradepulse.core.neuro.serotonin")
    sys.modules["core.neuro.serotonin.serotonin_controller"] = _sero_mod
except ImportError:
    pass
