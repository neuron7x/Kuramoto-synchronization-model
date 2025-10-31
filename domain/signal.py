"""Compatibility layer for signal domain entity.

The canonical implementation lives under :mod:`domain.signals`.
"""

from __future__ import annotations

from .signals import ModelMetadata, Signal, SignalAction

__all__ = ["ModelMetadata", "Signal", "SignalAction"]
