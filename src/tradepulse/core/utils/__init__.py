"""Shim utils module routed to legacy core.utils."""

from __future__ import annotations

__CANONICAL__ = True

import importlib.util
import sys
from pathlib import Path
from typing import Iterable


def _find_legacy_utils_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "core" / "utils"
        if candidate.exists():
            return candidate
    raise ImportError("Unable to locate legacy core/utils directory")


_LEGACY_DIR = _find_legacy_utils_dir()
_LEGACY_INIT = _LEGACY_DIR / "__init__.py"
_spec = importlib.util.spec_from_file_location(
    "core.utils", _LEGACY_INIT, submodule_search_locations=[str(_LEGACY_DIR)]
)
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
    raise ImportError("Unable to locate legacy core.utils")
_legacy_pkg = importlib.util.module_from_spec(_spec)
sys.modules["core.utils"] = _legacy_pkg
_spec.loader.exec_module(_legacy_pkg)

globals().update(_legacy_pkg.__dict__)
__all__: Iterable[str] = getattr(_legacy_pkg, "__all__", tuple())
