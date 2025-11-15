"""Utilities for harmonising the installed `tradepulse` namespace.

The repository exposes rich packages such as :mod:`backtest` and
:mod:`execution` at the repository root.  When the project is installed as a
wheel, however, only the namespaced modules under ``src/tradepulse`` are
available to consumers.  To avoid duplicating implementation files we expose a
small helper that mirrors the public API of the source packages while keeping
runtime imports fast and explicit.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from types import ModuleType
from typing import Iterable, Tuple


def _normalise_public_names(source: ModuleType, exported: Iterable[str] | None) -> Tuple[str, ...]:
    """Return a stable list of public attributes for *source*.

    Preference is given to ``__all__`` when provided so that we respect the
    curated public API of the underlying package.  When ``__all__`` is not
    defined we derive the exports from the attribute list while filtering out
    private names.
    """

    if exported is not None:
        return tuple(dict.fromkeys(exported))

    discovered = getattr(source, "__all__", None)
    if discovered:
        return tuple(dict.fromkeys(discovered))

    return tuple(name for name in dir(source) if not name.startswith("_"))


def bridge_namespace(
    local_module_name: str,
    source_package: str,
    *,
    exported_names: Iterable[str] | None = None,
) -> Tuple[str, ...]:
    """Mirror *source_package* into *local_module_name*.

    The helper re-exports public attributes from the source package, registers
    submodules so ``import tradepulse.backtest.engine`` resolves correctly, and
    wires ``__getattr__``/``__dir__`` for an ergonomic interactive experience.

    The tuple of exported symbols is returned so callers can assign it to
    ``__all__``.
    """

    module = sys.modules[local_module_name]
    source = importlib.import_module(source_package)

    public_names = _normalise_public_names(source, exported_names)

    for name in public_names:
        if hasattr(source, name):
            setattr(module, name, getattr(source, name))

    def _module_getattr(attribute: str) -> object:
        if hasattr(source, attribute):
            return getattr(source, attribute)
        message = f"module '{local_module_name}' has no attribute '{attribute}'"
        raise AttributeError(message) from None

    def _module_dir() -> list[str]:
        merged = set(module.__dict__)
        merged.update(dir(source))
        return sorted(merged)

    module.__all__ = public_names
    module.__getattr__ = _module_getattr  # type: ignore[attr-defined]
    module.__dir__ = _module_dir  # type: ignore[attr-defined]

    if getattr(source, "__doc__", None):
        module.__doc__ = module.__doc__ or source.__doc__

    if hasattr(source, "__path__"):
        module.__path__ = getattr(source, "__path__")  # type: ignore[attr-defined]

        prefix_source = f"{source_package}."
        prefix_local = f"{local_module_name}."

        for finder, name, _ in pkgutil.iter_modules(source.__path__):
            target_name = f"{prefix_source}{name}"
            alias_name = f"{prefix_local}{name}"
            if alias_name in sys.modules:
                continue
            submodule = importlib.import_module(target_name)
            sys.modules[alias_name] = submodule
            setattr(module, name, submodule)

    return public_names


__all__ = ["bridge_namespace"]
