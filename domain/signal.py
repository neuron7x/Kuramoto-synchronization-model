"""Compatibility layer for signal domain entity.

The canonical implementation lives under :mod:`domain.signals`.
"""

from __future__ import annotations

from .signals import Signal, SignalAction

__all__ = ["Signal", "SignalAction"]
