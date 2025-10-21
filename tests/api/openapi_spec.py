"""Shared helpers for accessing the canonical OpenAPI specification."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_RELATIVE_PATH = Path("schemas/openapi/tradepulse-online-inference-v1.json")
EXPECTED_OPENAPI_VERSION = "0.2.0"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def openapi_spec_path() -> Path:
    """Return the absolute path to the persisted OpenAPI document."""
    return _repo_root() / _SPEC_RELATIVE_PATH


@lru_cache(maxsize=1)
def load_expected_openapi_schema() -> dict[str, Any]:
    """Load and cache the expected OpenAPI schema from disk."""
    spec_path = openapi_spec_path()
    return json.loads(spec_path.read_text(encoding="utf-8"))
