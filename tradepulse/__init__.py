"""TradePulse public Python package.

This shim keeps backward compatibility with non-src based tooling while the
project transitions to the unified protocol layout.  All heavy lifting lives
under ``src.tradepulse`` so that packaging metadata remains consistent.
"""

from importlib import import_module
import os
from types import ModuleType
from typing import TYPE_CHECKING

_MODULE_NAME = "src.tradepulse"
_LIGHT_EXPORTS = {"neural_controller": "tradepulse.neural_controller"}


def _light_mode_enabled() -> bool:
    value = os.environ.get("TRADEPULSE_LIGHT_IMPORT")
    if value is None:
        return True
    return value == "1" or value.lower() in {"true", "yes"}


def __getattr__(name: str) -> ModuleType:
    if _light_mode_enabled():
        target = _LIGHT_EXPORTS.get(name)
        if target is None:
            raise AttributeError(name)
        module = import_module(target)
        globals()[name] = module
        return module
    module = import_module(_MODULE_NAME)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover - best effort reflection hook.
    if _light_mode_enabled():
        return sorted(set(list(globals()) + list(_LIGHT_EXPORTS)))
    module = import_module(_MODULE_NAME)
    return sorted(set(dir(module)))


if not TYPE_CHECKING and not _light_mode_enabled():
    globals().update(import_module(_MODULE_NAME).__dict__)
