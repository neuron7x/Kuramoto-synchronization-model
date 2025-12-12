"""Forwarder shim to the canonical ``src.tradepulse`` package."""

from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

_MODULE_NAME = "src.tradepulse"
_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "tradepulse"

# Allow Python to locate modules under src/tradepulse when importing via the shim name.
__path__ = [str(_SRC_PACKAGE)] if _SRC_PACKAGE.exists() else []
if __spec__ is not None and __spec__.submodule_search_locations is not None:
    __spec__.submodule_search_locations = __path__


def __getattr__(name: str) -> ModuleType:
    module = import_module(f"{_MODULE_NAME}.{name}")
    globals()[name] = module
    return module


if TYPE_CHECKING:
    # During type checking, expose the canonical module attributes eagerly.
    _module = import_module(_MODULE_NAME)
    globals().update(_module.__dict__)
    __all__ = getattr(_module, "__all__", [])
