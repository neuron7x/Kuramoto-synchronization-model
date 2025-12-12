from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_SITE_FILE = _REPO_ROOT / "sitecustomize.py"

if _SITE_FILE.exists():
    spec = importlib.util.spec_from_file_location("_tradepulse_sitecustomize", _SITE_FILE)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("_tradepulse_sitecustomize", module)
        spec.loader.exec_module(module)
