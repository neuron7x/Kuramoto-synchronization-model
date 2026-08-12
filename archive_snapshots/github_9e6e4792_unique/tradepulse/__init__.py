"""TradePulse public Python package.

Canonical public namespace: ``tradepulse.*``.

This shim keeps backward compatibility with non-src based tooling while the
project transitions to the unified protocol layout. All heavy lifting lives
under ``src.tradepulse`` so that packaging metadata remains consistent. Avoid
importing ``src.*`` directly in new code.
"""

__CANONICAL__ = False

import os
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

_PROFILE = os.environ.get("TRADEPULSE_PROFILE", os.environ.get("APP_ENV", "dev")).lower()

# Provide a benign default for the admin API two-factor secret only in local/test
# environments. Production-like profiles must supply real secrets explicitly.
if _PROFILE in {"dev", "development", "test", "ci", "local"}:
    os.environ.setdefault("TRADEPULSE_TWO_FACTOR_SECRET", "JBSWY3DPEHPK3PXP")
    os.environ.setdefault("ADMIN_API_SETTINGS__two_factor_secret", "JBSWY3DPEHPK3PXP")
else:
    if "TRADEPULSE_TWO_FACTOR_SECRET" not in os.environ and "ADMIN_API_SETTINGS__two_factor_secret" not in os.environ:
        msg = "Two-factor secret must be configured for non-development profiles"
        raise RuntimeError(msg)

os.environ.setdefault("TRADEPULSE_BOOTSTRAP_STRATEGY", "lazy")

_MODULE_NAME = "src.tradepulse"
_LIGHT_EXPORTS = {"neural_controller": "tradepulse.neural_controller"}

_PACKAGE_ROOT = Path(__file__).resolve().parent
_SRC_PACKAGE = _PACKAGE_ROOT.parent / "src" / "tradepulse"

__path__ = [str(_PACKAGE_ROOT)]  # type: ignore[assignment]
if _SRC_PACKAGE.exists():
    src_path = str(_SRC_PACKAGE)
    if src_path not in __path__:
        __path__.append(src_path)
    if __spec__ is not None and __spec__.submodule_search_locations is not None:
        locations = list(__spec__.submodule_search_locations)
        if src_path not in locations:
            locations.append(src_path)
            __spec__.submodule_search_locations = locations


def _light_mode_enabled() -> bool:
    value = os.environ.get("TRADEPULSE_LIGHT_IMPORT")
    if value is None:
        return True
    return value == "1" or value.lower() in {"true", "yes"}


def __getattr__(name: str) -> ModuleType:
    if _light_mode_enabled():
        target = _LIGHT_EXPORTS.get(name)
        if target is not None:
            module = import_module(target)
            globals()[name] = module
            return module
        # fall back to pulling the attribute from the canonical src.tradepulse
        # package without importing the entire module eagerly. This keeps the
        # lightweight shim behaviour while still supporting imports such as
        # ``import tradepulse.sdk`` used across the codebase.
        try:
            module = import_module(f"{_MODULE_NAME}.{name}")
        except ModuleNotFoundError as exc:  # pragma: no cover - mirrors stdlib
            raise AttributeError(name) from exc
        sys.modules.setdefault(f"{__name__}.{name}", module)
        globals()[name] = module
        return module
    module = import_module(_MODULE_NAME)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover - best effort reflection hook.
    if _light_mode_enabled():
        names = set(globals()) | set(_LIGHT_EXPORTS)
        try:
            src_module = import_module(_MODULE_NAME)
            names |= set(dir(src_module))
        except ModuleNotFoundError:  # pragma: no cover - defensive
            pass
        return sorted(names)
    module = import_module(_MODULE_NAME)
    return sorted(set(dir(module)))


if not TYPE_CHECKING and not _light_mode_enabled():
    globals().update(import_module(_MODULE_NAME).__dict__)
