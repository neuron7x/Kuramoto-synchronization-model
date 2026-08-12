# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim-safe descriptor-metadata factory.

GeoSync's canonical positioning is a verification-first quantitative
*research* platform: every descriptor it emits describes a past or present
state, and is explicitly **not** a predictor, **not** a trade signal, and
**not** investment advice. That boundary is easy to assert in prose and
easy to forget in code. This module makes the boundary a *construction
invariant* instead of a documentation footnote.

:func:`build_descriptor_metadata` returns the standard metadata block that
every descriptor should carry. It does three things that cannot be skipped
by a caller:

* it always stamps the three claim fields
  (``claim_boundary="descriptor_only_not_predictor"``,
  ``not_predictive_claim=True``, ``not_financial_advice=True``);
* it fails closed (``ValueError``) if any forbidden trading/prediction
  token appears in the ``method``/``source``/``extra`` text the caller
  supplies, so a descriptor cannot quietly re-label itself as a signal;
* it fails closed on non-finite or negative counts, so the provenance
  counters cannot carry ``NaN``/``inf``/negative garbage downstream.

The forbidden tokens live in a list-literal denylist
(:data:`FORBIDDEN_DESCRIPTOR_TERMS`); they are identifiers/data here, not a
product promise, so the canonical claim-boundary gate
(``scripts/ci/check_claim_boundary.py``) — which scans docs/code *prose*,
not denylist data — is unaffected.

The factory has no dependency beyond the standard library, is fully type
annotated, and is deterministic: identical inputs yield an identical block.
"""

from __future__ import annotations

import math
import re
from typing import Any, Final

# Canonical claim-boundary constants. These are the exact strings every
# GeoSync descriptor must carry so the boundary is machine-checkable.
CLAIM_BOUNDARY: Final[str] = "descriptor_only_not_predictor"

# The mandatory keys this factory always stamps. A caller-supplied ``extra``
# mapping may never overwrite any of these — that is the whole point.
MANDATORY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "claim_boundary",
        "not_predictive_claim",
        "not_financial_advice",
        "method",
        "source",
        "input_count",
        "invalid_count",
        "valid_count",
    }
)

# Forbidden trading / prediction vocabulary. Presence of any of these tokens
# in caller-supplied ``method`` / ``source`` / ``extra`` text means the
# descriptor is being re-framed as a tradeable signal or a forecast, which
# violates the descriptor-only boundary. Kept as a list-literal of bare
# identifiers (data, not prose) so the claim-boundary prose gate does not
# treat this denylist as a product claim.
FORBIDDEN_DESCRIPTOR_TERMS: Final[frozenset[str]] = frozenset(
    [
        "buy",
        "sell",
        "long",
        "short",
        "entry",
        "exit",
        "alpha",
        "edge",
        "profit",
        "predictor",
        "forecast",
        "guaranteed",
    ]
)

# Whole-word matcher over the denylist. Word boundaries stop substrings of
# innocuous words (e.g. "method", "shortfall") from false-positiving, while
# still catching "buy"/"sell"/"alpha" as standalone tokens. Case-folded.
_FORBIDDEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in sorted(FORBIDDEN_DESCRIPTOR_TERMS)) + r")\b",
    re.IGNORECASE,
)


def _iter_text_fragments(value: Any) -> list[str]:
    """Flatten an arbitrary JSON-ish value into its string fragments.

    Used to scan caller-supplied ``extra`` content for forbidden tokens
    regardless of nesting. Keys *and* values of mappings are scanned, since
    a forbidden token can hide in either.
    """
    fragments: list[str] = []
    if isinstance(value, str):
        fragments.append(value)
    elif isinstance(value, dict):
        for key, sub in value.items():
            if isinstance(key, str):
                fragments.append(key)
            fragments.extend(_iter_text_fragments(sub))
    elif isinstance(value, (list, tuple, set, frozenset)):
        for sub in value:
            fragments.extend(_iter_text_fragments(sub))
    return fragments


def _assert_clean(label: str, value: Any) -> None:
    """Raise ``ValueError`` if any forbidden token appears in *value*."""
    for fragment in _iter_text_fragments(value):
        match = _FORBIDDEN_RE.search(fragment)
        if match is not None:
            raise ValueError(
                f"forbidden descriptor term {match.group(0)!r} in {label!r}: "
                f"a descriptor must not be framed as a trade signal or forecast "
                f"(claim boundary {CLAIM_BOUNDARY!r})"
            )


def _validate_count(label: str, value: int) -> int:
    """Validate a provenance counter: a finite, non-negative integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an int, got {type(value).__name__}")
    # int is always finite; the explicit check documents the contract and
    # guards against a float sneaking in via a permissive caller.
    if not math.isfinite(value):  # pragma: no cover - unreachable for int
        raise ValueError(f"{label} must be finite, got {value!r}")
    if value < 0:
        raise ValueError(f"{label} must be non-negative, got {value!r}")
    return value


def build_descriptor_metadata(
    *,
    method: str,
    source: str,
    input_count: int,
    invalid_count: int = 0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical claim-safe descriptor-metadata block.

    The returned mapping always carries the three claim-boundary fields and
    the provenance counters. It is the single place GeoSync stamps the
    descriptor-only boundary, so that boundary is impossible to forget and
    is enforced at construction time.

    Parameters
    ----------
    method:
        Short identifier of the descriptor method (e.g. ``"hurst_rs"``).
        Must not contain any forbidden trading/prediction token.
    source:
        Provenance of the input (e.g. ``"ohlcv_close_1m"``). Must not
        contain any forbidden trading/prediction token.
    input_count:
        Total number of observations considered. Finite, non-negative int.
    invalid_count:
        Number of observations rejected as invalid (non-finite, etc.).
        Finite, non-negative int, and never greater than ``input_count``.
    extra:
        Optional supplementary metadata. Merged into the block, but may
        **never** overwrite a mandatory key, and is scanned (keys and
        values, recursively) for forbidden tokens.

    Returns
    -------
    dict[str, Any]
        A fresh metadata mapping. Identical inputs yield an identical block.

    Raises
    ------
    ValueError
        If ``method``/``source`` is empty, if any forbidden token appears
        in ``method``/``source``/``extra``, if a count is non-finite or
        negative, if ``invalid_count`` exceeds ``input_count``, or if
        ``extra`` attempts to overwrite a mandatory key.
    """
    if not isinstance(method, str) or not method.strip():
        raise ValueError("method must be a non-empty string")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be a non-empty string")

    _assert_clean("method", method)
    _assert_clean("source", source)

    input_n = _validate_count("input_count", input_count)
    invalid_n = _validate_count("invalid_count", invalid_count)
    if invalid_n > input_n:
        raise ValueError(f"invalid_count ({invalid_n}) must not exceed input_count ({input_n})")

    merged_extra: dict[str, Any] = {}
    if extra is not None:
        if not isinstance(extra, dict):
            raise ValueError(f"extra must be a dict or None, got {type(extra).__name__}")
        _assert_clean("extra", extra)
        collisions = MANDATORY_KEYS & set(extra.keys())
        if collisions:
            raise ValueError(f"extra must not overwrite mandatory key(s): {sorted(collisions)}")
        merged_extra = dict(extra)

    metadata: dict[str, Any] = {
        # Mandatory claim-boundary stamp — always present, always these values.
        "claim_boundary": CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "not_financial_advice": True,
        # Provenance.
        "method": method,
        "source": source,
        "input_count": input_n,
        "invalid_count": invalid_n,
        "valid_count": input_n - invalid_n,
    }
    # Caller extras go last but cannot collide (checked above), so the
    # mandatory fields are guaranteed intact.
    metadata.update(merged_extra)
    return metadata
