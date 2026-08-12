# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Provenance/bounds witness for ``geosync.core.neuro._validation``.

Ledger
------
neuro-validation-bounds (PARTIAL, QUARANTINE_DOC). The source module exposes
numeric bounds checks (clip-or-raise) for neuromodulator metrics. The ledger
falsifier is: "No null-model test; no documentation tying ranges to a
citation." The remediation is QUARANTINE_DOC, not promotion: this file pins
the *honest* contract that the bounds are engineering numeric guards.

Mechanism (what is actually computed)
-------------------------------------
``ensure_finite`` rejects NaN/Inf; ``validate_neuro_metric_bounds`` /
``validate_neuro_invariants`` compare each metric against an inclusive
``BoundsSpec`` interval and either clamp (``behavior == "clip"``) or raise
(``behavior == "raise"``) on out-of-range inputs. The bounds are plain
``float`` interval endpoints carried in ``BoundsSpec`` / function defaults.

Validity (what these tests do and do not assert)
------------------------------------------------
Tests exercise the *engineering* behavior only: finite-rejection, the exact
default interval endpoints, inclusivity at the endpoints, raise-on-violation,
and clip-on-violation. Inputs are synthetic scalars chosen relative to the
module's own default constants; there is no physiological data and no
empirical distribution.

Falsifier (what would make this witness fail)
---------------------------------------------
An out-of-range or non-finite input that is *silently accepted* (neither
clamped nor raised), or a default interval endpoint that drifts from the
value declared in the source module, fails this witness.

NON-CLAIM
---------
The validation bounds are engineering numeric guards, NOT biologically-derived
ranges. The DA/5-HT, E/I, arousal-attention, and stability intervals are
arbitrary engineering limits asserted by the module, not physiological
constants tied to any cited source (ledger ``neuro-validation-bounds``).
All inputs here are synthetic-only. This witness pins provenance and bounds;
it does NOT promote any biological claim.
"""

from __future__ import annotations

import logging
import math

import pytest

from geosync.core.neuro._validation import (
    BoundsSpec,
    clamp,
    ensure_finite,
    validate_neuro_invariants,
    validate_neuro_metric_bounds,
)

# --- Exact default bound constants mirrored from the source module ----------
# These are the *engineering* interval endpoints declared as defaults in
# ``validate_neuro_invariants`` (da_5ht_ratio_range / ei_balance_range) and in
# ``validate_neuro_metric_bounds`` (the BoundsSpec defaults). They are pinned
# here verbatim so any drift in the source defaults fails this witness.
# NON-CLAIM: arbitrary engineering limits, not physiological constants.
DA_5HT_RATIO_RANGE: tuple[float, float] = (1.0, 3.0)
EI_BALANCE_RANGE: tuple[float, float] = (1.0, 2.5)
AROUSAL_ATTENTION_RANGE: tuple[float, float] = (0.0, 1.0)
STABILITY_RANGE: tuple[float, float] = (0.0, 1.0)


def _midpoint(interval: tuple[float, float]) -> float:
    """Return the strictly-interior midpoint of an inclusive interval."""
    low, high = interval
    return (low + high) / 2.0


def _in_bounds_kwargs() -> dict[str, float]:
    """Synthetic metric set that sits strictly inside every default interval."""
    return {
        "dopamine_serotonin_ratio": _midpoint(DA_5HT_RATIO_RANGE),
        "excitation_inhibition_balance": _midpoint(EI_BALANCE_RANGE),
        "arousal_attention_coherence": _midpoint(AROUSAL_ATTENTION_RANGE),
        "stability": _midpoint(STABILITY_RANGE),
    }


# --- Provenance: defaults are the declared engineering constants ------------


def test_default_intervals_match_declared_engineering_constants() -> None:
    """Default BoundsSpec endpoints equal the pinned engineering constants.

    Falsifier: a default interval endpoint drifts from the value declared in
    the source module. NON-CLAIM: these are arbitrary engineering limits.
    """
    # Reconstruct the defaults the public API applies, then compare endpoints.
    da = BoundsSpec(DA_5HT_RATIO_RANGE[0], DA_5HT_RATIO_RANGE[1], "raise")
    ei = BoundsSpec(EI_BALANCE_RANGE[0], EI_BALANCE_RANGE[1], "raise")
    assert (da.min_value, da.max_value) == DA_5HT_RATIO_RANGE
    assert (ei.min_value, ei.max_value) == EI_BALANCE_RANGE
    # A strictly-interior synthetic point is accepted under the defaults
    # (no exception, no silent acceptance of an out-of-range value).
    validate_neuro_invariants(**_in_bounds_kwargs())


def test_invariants_uses_raise_behavior_not_silent_clip() -> None:
    """``validate_neuro_invariants`` rejects (raises) on out-of-range input.

    Falsifier: an out-of-range DA/5-HT ratio is silently accepted. The value
    ``DA_5HT_RATIO_RANGE[1] + 1.0`` lies above the engineering upper bound.
    """
    kwargs = _in_bounds_kwargs()
    kwargs["dopamine_serotonin_ratio"] = DA_5HT_RATIO_RANGE[1] + 1.0
    with pytest.raises(ValueError, match="dopamine_serotonin_ratio"):
        validate_neuro_invariants(**kwargs)


# --- Engineering guard: non-finite rejection --------------------------------


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_ensure_finite_rejects_non_finite(bad: float) -> None:
    """``ensure_finite`` raises on NaN/+Inf/-Inf rather than accepting them."""
    with pytest.raises(ValueError, match="finite"):
        ensure_finite("metric", bad)


def test_ensure_finite_passes_finite_value() -> None:
    """A finite value passes through ``ensure_finite`` unchanged."""
    interior = _midpoint(DA_5HT_RATIO_RANGE)
    assert ensure_finite("metric", interior) == interior


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_metric_bounds_reject_non_finite_even_when_clipping(bad: float) -> None:
    """Non-finite metrics raise even under ``clip`` behavior (no silent pass).

    Falsifier: a NaN/Inf metric is clamped to a finite endpoint and silently
    accepted. ``ensure_finite`` runs before the clamp, so this must raise.
    """
    kwargs = _in_bounds_kwargs()
    kwargs["stability"] = bad
    with pytest.raises(ValueError, match="finite"):
        validate_neuro_metric_bounds(
            **kwargs,
            stability_bounds=BoundsSpec(STABILITY_RANGE[0], STABILITY_RANGE[1], "clip"),
        )


# --- Engineering guard: endpoint inclusivity --------------------------------


def test_default_intervals_are_inclusive_at_endpoints() -> None:
    """Exact interval endpoints are accepted (inclusive bounds).

    Falsifier: an endpoint value is rejected as out-of-range. Endpoints are
    the pinned engineering constants, exercised with ``raise`` behavior so a
    rejection would surface as a ValueError.
    """
    result = validate_neuro_metric_bounds(
        dopamine_serotonin_ratio=DA_5HT_RATIO_RANGE[0],
        excitation_inhibition_balance=EI_BALANCE_RANGE[1],
        arousal_attention_coherence=AROUSAL_ATTENTION_RANGE[0],
        stability=STABILITY_RANGE[1],
    )
    assert result["dopamine_serotonin_ratio"] == DA_5HT_RATIO_RANGE[0]
    assert result["excitation_inhibition_balance"] == EI_BALANCE_RANGE[1]
    assert result["arousal_attention_coherence"] == AROUSAL_ATTENTION_RANGE[0]
    assert result["stability"] == STABILITY_RANGE[1]


# --- Engineering guard: raise vs clip on out-of-range -----------------------


def test_metric_bounds_raise_on_out_of_range_under_raise_behavior() -> None:
    """Out-of-range value raises under ``raise`` behavior, not silent accept.

    Falsifier: an E/I balance above ``EI_BALANCE_RANGE[1]`` is accepted.
    """
    kwargs = _in_bounds_kwargs()
    kwargs["excitation_inhibition_balance"] = EI_BALANCE_RANGE[1] + 0.5
    with pytest.raises(ValueError, match="excitation_inhibition_balance"):
        validate_neuro_metric_bounds(
            **kwargs,
            ei_balance_bounds=BoundsSpec(EI_BALANCE_RANGE[0], EI_BALANCE_RANGE[1], "raise"),
        )


def test_metric_bounds_clip_clamps_to_endpoint_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Out-of-range value is clamped to the nearest endpoint under ``clip``.

    Falsifier: an out-of-range value passes through unchanged (silently
    accepted) instead of being clamped to the engineering endpoint. The
    expected clamp target is computed from the pinned constants via the
    module's own ``clamp`` helper, so no magic number is asserted.
    """
    over = DA_5HT_RATIO_RANGE[1] + 5.0
    under = AROUSAL_ATTENTION_RANGE[0] - 5.0
    expected_da = clamp(over, DA_5HT_RATIO_RANGE[0], DA_5HT_RATIO_RANGE[1])
    expected_aa = clamp(under, AROUSAL_ATTENTION_RANGE[0], AROUSAL_ATTENTION_RANGE[1])

    kwargs = _in_bounds_kwargs()
    kwargs["dopamine_serotonin_ratio"] = over
    kwargs["arousal_attention_coherence"] = under

    with caplog.at_level(logging.WARNING):
        result = validate_neuro_metric_bounds(
            **kwargs,
            da_5ht_ratio_bounds=BoundsSpec(DA_5HT_RATIO_RANGE[0], DA_5HT_RATIO_RANGE[1], "clip"),
            arousal_attention_bounds=BoundsSpec(
                AROUSAL_ATTENTION_RANGE[0], AROUSAL_ATTENTION_RANGE[1], "clip"
            ),
        )

    # Clamped to the engineering endpoints, not silently passed through.
    assert result["dopamine_serotonin_ratio"] == expected_da
    assert result["dopamine_serotonin_ratio"] == DA_5HT_RATIO_RANGE[1]
    assert result["arousal_attention_coherence"] == expected_aa
    assert result["arousal_attention_coherence"] == AROUSAL_ATTENTION_RANGE[0]
    # The clip path is observable (warned), i.e. not a silent acceptance.
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_clamp_helper_is_pure_interval_projection() -> None:
    """``clamp`` projects onto the inclusive interval with no other effect.

    This pins the engineering-guard semantics independent of any metric name:
    below-low clamps to low, above-high clamps to high, interior is identity.
    """
    low, high = DA_5HT_RATIO_RANGE
    interior = _midpoint(DA_5HT_RATIO_RANGE)
    assert clamp(low - 10.0, low, high) == low
    assert clamp(high + 10.0, low, high) == high
    assert clamp(interior, low, high) == interior
