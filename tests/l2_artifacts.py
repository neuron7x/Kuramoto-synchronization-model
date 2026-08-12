"""Shared helpers for loading L2 result artifacts in tests.

Every `tests/test_l2_*.py` file duplicates the same three-line helper:

    def _load(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

Plus the same skip-on-missing pattern:

    if not path.exists():
        pytest.skip(f"... not present")

This module consolidates both into three helpers:

    load_json(path)              — raises FileNotFoundError on missing
    load_json_or_skip(path)      — pytest.skip when missing, else dict
    load_results_artifact(name)  — shorthand for `results/<name>` + skip

Tests remain independently parameterizable; the helpers just remove the
boilerplate. Keeping this in `tests/` (not `conftest.py`) means we do
not pollute the fixture namespace of unrelated suites.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_RESULTS = Path("results")


def load_json(path: Path) -> dict[str, Any]:
    """Read a JSON file into a dict. Raises FileNotFoundError on missing."""
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def load_json_or_skip(path: Path, *, reason: str | None = None) -> dict[str, Any]:
    """Read JSON, or pytest.skip when the file is absent."""
    if not path.exists():
        pytest.skip(reason or f"{path} not present")
    return load_json(path)


def load_results_artifact(filename: str, *, reason: str | None = None) -> dict[str, Any]:
    """Shortcut: load `results/<filename>.json` or pytest.skip."""
    return load_json_or_skip(
        _RESULTS / filename,
        reason=reason or f"{filename} artifact not present",
    )
