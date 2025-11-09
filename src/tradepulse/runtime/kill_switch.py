"""Global kill-switch used by safety-critical components."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager

_LOCK = threading.Lock()
_ACTIVE = False


def is_kill_switch_active() -> bool:
    return _ACTIVE or os.getenv("TRADEPULSE_KILL_SWITCH", "0") == "1"


def activate_kill_switch() -> None:
    global _ACTIVE
    with _LOCK:
        _ACTIVE = True


def deactivate_kill_switch() -> None:
    global _ACTIVE
    with _LOCK:
        _ACTIVE = False


@contextmanager
def kill_switch_guard():
    activate_kill_switch()
    try:
        yield
    finally:
        deactivate_kill_switch()


__all__ = [
    "is_kill_switch_active",
    "activate_kill_switch",
    "deactivate_kill_switch",
    "kill_switch_guard",
]
