"""Test configuration for NaK controller package."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repository root is importable so ``nak_controller`` resolves even
# when pytest sets the rootdir to ``nak_controller``.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
