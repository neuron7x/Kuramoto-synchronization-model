# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Legacy package shim.

Canonical code lives under ``geosync`` (src/geosync). This package remains
for backward compatibility and forwards duplicated neuro modules to the
canonical implementations. Legacy-only modules (e.g., core.utils) continue to
reside here.
"""

from __future__ import annotations

import sys
from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    """Forward known duplicate symbols to the canonical geosync.core."""

    try:
        return getattr(import_module("geosync.core"), name)
    except Exception as exc:
        raise AttributeError(name) from exc


# Explicit aliasing for serotonin controllers to ensure object identity across
# legacy and canonical import paths.
try:  # pragma: no cover - best effort mapping
    _sero_mod = import_module("geosync.core.neuro.serotonin.serotonin_controller")
    sys.modules["core.neuro.serotonin"] = import_module("geosync.core.neuro.serotonin")
    sys.modules["core.neuro.serotonin.serotonin_controller"] = _sero_mod
except ImportError:
    pass
