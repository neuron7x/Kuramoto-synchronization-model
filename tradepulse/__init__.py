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


def __getattr__(name: str) -> ModuleType:
    if os.environ.get("TRADEPULSE_LIGHT_IMPORT") == "1":
        raise AttributeError(name)
    module = import_module(_MODULE_NAME)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover - best effort reflection hook.
    module = import_module(_MODULE_NAME)
    return sorted(set(dir(module)))


if not TYPE_CHECKING and os.environ.get("TRADEPULSE_LIGHT_IMPORT") != "1":
    globals().update(import_module(_MODULE_NAME).__dict__)
