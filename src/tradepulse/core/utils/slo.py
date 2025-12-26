from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_LEGACY_DIR = Path(__file__).resolve().parents[4] / "core" / "utils"
_LEGACY_FILE = _LEGACY_DIR / "slo.py"
_spec = importlib.util.spec_from_file_location(
    "core.utils.slo", _LEGACY_FILE, submodule_search_locations=[str(_LEGACY_DIR)]
)
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
    raise ImportError("Unable to locate legacy core.utils.slo")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules["core.utils.slo"] = _legacy
_spec.loader.exec_module(_legacy)

globals().update(_legacy.__dict__)
__all__ = [name for name in globals() if not name.startswith("_")]
