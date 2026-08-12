# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic continuous-to-discrete state quantization contract.

This module is a *state compiler*, not a forecaster. It maps finite
continuous numeric observations into a bounded, ordered set of discrete
descriptor states under an explicit fixed-threshold rule, while:

* preserving provenance (a config hash that pins the rule),
* declaring information loss (within-band magnitude is intentionally
  discarded),
* counting every non-finite observation as ``invalid`` instead of
  silently absorbing it into an extreme band, and
* failing closed on a malformed rule (unordered or non-finite
  thresholds, mismatched label cardinality).

The discrete states are structural descriptors of where each observation
falls relative to the declared thresholds. They carry no directional or
financial meaning: the contract asserts nothing about future prices,
returns, or profitability, and is research-only descriptor infrastructure.

Motivation
----------
The streaming quantizers in :mod:`analytics.signals.irreversibility`
(``ZScoreQuantizer`` / ``RollingRankQuantizer``) silently map a NaN or an
infinity onto a real band. That hides invalid input behind a valid-looking
state. This batch contract is the fail-explicit counterpart: every
information-losing or invalid mapping is declared in the returned metadata,
so a degenerate run is visible rather than disguised.

Worked example
--------------
>>> result = quantize_states(
...     [-2.0, 0.0, 0.4, float("nan")],
...     thresholds=[-0.5, 0.5],
...     labels=["low", "neutral", "high"],
... )
>>> list(result.states)
['low', 'neutral', 'neutral', 'invalid']
>>> result.metadata["invalid_count"]
1
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

__all__ = [
    "QuantizationStateResult",
    "quantize_states",
    "DEFAULT_INVALID_STATE",
    "TIE_POLICY",
    "OUTLIER_POLICY",
]

DEFAULT_INVALID_STATE = "invalid"

# A value exactly equal to a threshold maps to the upper adjacent band.
# This is ``numpy.searchsorted(..., side="right")`` and is stable and
# deterministic for repeated values.
TIE_POLICY = "value equal to a threshold maps to the upper adjacent state (searchsorted right)"

# Observations below the lowest threshold map to the first band and those
# above the highest threshold map to the last band; no state is ever emitted
# outside the declared label set.
OUTLIER_POLICY = "clamped to the extreme declared bands (no out-of-range state)"


@dataclass(frozen=True, slots=True)
class QuantizationStateResult:
    """Outcome of one deterministic quantization run.

    Attributes
    ----------
    states:
        Per-observation discrete descriptor labels, in input order. A
        non-finite observation yields ``invalid_state``.
    metadata:
        Complete, replayable provenance and information-loss record.
    """

    states: tuple[str, ...]
    metadata: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialise states and metadata for logging / replay manifests."""
        return {"states": list(self.states), "metadata": dict(self.metadata)}


def _validate_thresholds(thresholds: Sequence[float]) -> list[float]:
    """Return thresholds as floats, failing closed on a malformed rule."""
    values = [float(t) for t in thresholds]
    if any(not math.isfinite(t) for t in values):
        raise ValueError(
            "quantize_states: thresholds must all be finite; "
            f"got {values!r}. A non-finite threshold makes the band rule "
            "undefined (fail-closed)."
        )
    for lower, upper in zip(values, values[1:]):
        if not lower < upper:
            raise ValueError(
                "quantize_states: thresholds must be strictly increasing; "
                f"got {values!r}. Equal or descending thresholds make the "
                "state mapping ambiguous (fail-closed)."
            )
    return values


def _config_hash(thresholds: Sequence[float], labels: Sequence[str], invalid_state: str) -> str:
    """Deterministic provenance hash that pins the quantization rule."""
    payload = json.dumps(
        {
            "thresholds": [float(t) for t in thresholds],
            "labels": list(labels),
            "invalid_state": invalid_state,
            "tie_policy": TIE_POLICY,
            "outlier_policy": OUTLIER_POLICY,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def quantize_states(
    values: Sequence[float],
    *,
    thresholds: Sequence[float],
    labels: Sequence[str],
    invalid_state: str = DEFAULT_INVALID_STATE,
) -> QuantizationStateResult:
    """Quantize continuous observations into bounded discrete descriptor states.

    Parameters
    ----------
    values:
        Finite continuous numeric observations. Non-finite entries
        (``NaN`` / ``+/-inf``) are mapped to ``invalid_state`` and counted,
        never silently placed in a real band.
    thresholds:
        ``K - 1`` strictly increasing finite cut points for ``K`` labels.
    labels:
        ``K`` ordered descriptor labels (the declared state set). Must not
        contain ``invalid_state``.
    invalid_state:
        Sentinel label assigned to every non-finite observation.

    Returns
    -------
    QuantizationStateResult
        ``states`` (per-observation labels) and a complete ``metadata``
        record declaring method, thresholds, counts, policies, the config
        hash, declared information loss, and the claim boundary.

    Raises
    ------
    ValueError
        On a malformed rule: thresholds non-finite or not strictly
        increasing, label cardinality ``!= len(thresholds) + 1``, or
        ``invalid_state`` colliding with a declared label. The contract
        fails closed rather than emitting an ambiguous mapping.
    """
    label_list = [str(label) for label in labels]
    threshold_list = _validate_thresholds(thresholds)

    if len(label_list) != len(threshold_list) + 1:
        raise ValueError(
            "quantize_states: need exactly len(thresholds)+1 labels; "
            f"got {len(label_list)} labels for {len(threshold_list)} thresholds."
        )
    if invalid_state in label_list:
        raise ValueError(
            "quantize_states: invalid_state "
            f"{invalid_state!r} must not collide with a declared band label."
        )

    boundaries = np.asarray(threshold_list, dtype=float)
    states: list[str] = []
    finite_count = 0
    invalid_count = 0
    band_counts: Counter[str] = Counter()

    for raw in values:
        x = float(raw)
        if not math.isfinite(x):
            states.append(invalid_state)
            invalid_count += 1
            continue
        band = int(np.searchsorted(boundaries, x, side="right"))
        # bounds: searchsorted already yields [0, len(boundaries)]; this clamp
        # only guards against a degenerate empty-threshold rule and never
        # emits a state outside the declared label set (OUTLIER_POLICY).
        band = min(max(band, 0), len(label_list) - 1)
        label = label_list[band]
        states.append(label)
        band_counts[label] += 1
        finite_count += 1

    input_count = len(states)
    metadata: dict[str, Any] = {
        "method": "fixed_threshold",
        "labels": list(label_list),
        "thresholds": list(threshold_list),
        "invalid_state": invalid_state,
        "input_count": input_count,
        "finite_count": finite_count,
        "invalid_count": invalid_count,
        "empty_input": input_count == 0,
        "tie_policy": TIE_POLICY,
        "outlier_policy": OUTLIER_POLICY,
        "state_counts": {label: band_counts.get(label, 0) for label in label_list},
        "config_hash": _config_hash(threshold_list, label_list, invalid_state),
        "information_loss": (
            "continuous magnitude within each band is discarded; only the "
            f"ordinal band (1 of {len(label_list)}) is retained"
        ),
        "information_loss_declared": True,
        "claim_boundary": "descriptor_only_not_predictor",
        "not_financial_advice": True,
        "not_predictive_claim": True,
    }
    return QuantizationStateResult(states=tuple(states), metadata=metadata)
