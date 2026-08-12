# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync physical-contracts layer.

This package turns the implicit physics of the 10 core modules (Kuramoto,
Ricci, Serotonin, Dopamine, GABA, ECS, HPC, Kelly, OMS, SignalBus) into a
machine-checkable catalog of laws, plus the plumbing that lets tests declare
themselves as *mathematical witnesses* of specific laws.

Public surface
--------------
- ``load_catalog()``          — parse ``catalog.yaml`` into typed ``Law`` objects.
- ``get_law(law_id)``         — fetch a single law by its dotted identifier.
- ``law(law_id, **kwargs)``   — decorator that binds a pytest function to a law.
- ``WITNESS_REGISTRY``        — global registry populated by ``@law`` at import time.
- ``LawViolationError``       — raised by witness helpers when a law is violated.

The decorator and registry live in ``physics_contracts.law`` to keep
``__init__`` import-cheap (no YAML parse on import).
"""

from __future__ import annotations

from .law import (
    WITNESS_REGISTRY,
    Law,
    LawViolationError,
    get_law,
    law,
    load_catalog,
)

__all__ = [
    "Law",
    "LawViolationError",
    "WITNESS_REGISTRY",
    "get_law",
    "law",
    "load_catalog",
]
