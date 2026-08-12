# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Observability-as-code helpers for GeoSync."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = ["build_bundle", "ObservabilityConfigError"]

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from .builder import ObservabilityConfigError, build_bundle


def __getattr__(name: str) -> Any:
    if name in __all__:
        module = import_module(".builder", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
