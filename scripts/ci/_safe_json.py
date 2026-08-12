# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed JSON parsing for CI gates.

Python's :func:`json.loads` accepts the non-standard tokens ``NaN``,
``Infinity`` and ``-Infinity`` by default. That is a fail-OPEN hazard for any
gate that reduces a JSON payload to a numeric total: a single ``NaN`` poisons
the reduction (``sum`` becomes ``nan``), and every ordering test against it is
false (``nan > base`` is ``False``), so a debt/growth check silently PASSES.

This module refuses those tokens outright and guarantees the parsed value is a
``dict`` using a real ``if/raise`` (NOT ``assert``) so the shape guard survives
``python -O``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class NonFiniteJSONError(ValueError):
    """Raised when a JSON payload carries NaN/Infinity/-Infinity."""


def _reject_constant(token: str) -> Any:
    """``parse_constant`` hook: any of NaN/Infinity/-Infinity is a hard error."""
    raise NonFiniteJSONError(
        f"non-finite JSON constant {token!r} is not permitted "
        "(NaN/Infinity poison numeric reductions and defeat ordering checks)"
    )


def loads_finite(text: str) -> Any:
    """Parse JSON text, rejecting NaN/Infinity/-Infinity via ``parse_constant``."""
    return json.loads(text, parse_constant=_reject_constant)


def loads_finite_dict(text: str) -> dict[str, Any]:
    """Parse JSON text and require the top-level value to be a ``dict``.

    Rejects non-finite constants and enforces the dict shape with an
    ``if/raise`` so ``python -O`` cannot strip the guard.
    """
    obj = loads_finite(text)
    if not isinstance(obj, dict):
        raise TypeError(f"expected a JSON object (dict), got {type(obj).__name__}")
    return obj


def load_finite_dict(path: str | Path) -> dict[str, Any]:
    """Read ``path`` as UTF-8 JSON, rejecting non-finite constants, require dict."""
    return loads_finite_dict(Path(path).read_text(encoding="utf-8"))
