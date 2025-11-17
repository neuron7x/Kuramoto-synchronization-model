"""Property-based coverage for HNCM math primitives."""

from __future__ import annotations

import math

import pytest

try:  # pragma: no cover - optional dependency
    from hypothesis import given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover - executed when Hypothesis missing
    pytest.skip("hypothesis not installed", allow_module_level=True)

from analytics.regime.src.consensus.hncm_adapter import clamp, ema
from tests.property.utils import property_settings, regression_note

# Hypothesis struggles with NaN/Inf comparisons for these helpers, so we
# constrain to finite numbers that still span a wide dynamic range.
_floats = st.floats(
    min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False, width=64
)


@given(
    x=_floats,
    interval=st.builds(
        lambda a, b: (a, b) if a <= b else (b, a),
        _floats,
        _floats,
    ),
)
@settings(**property_settings("test_clamp_respects_bounds"))
def test_clamp_respects_bounds(x: float, interval: tuple[float, float]) -> None:
    lo, hi = interval
    result = clamp(x, lo, hi)
    regression_note("clamp", {"x": x, "lo": lo, "hi": hi, "result": result})

    assert lo <= result <= hi
    if lo <= x <= hi:
        assert result == pytest.approx(x)
    elif x < lo:
        assert result == pytest.approx(lo)
    else:
        assert result == pytest.approx(hi)


@given(
    ordered_pair=st.builds(
        lambda a, b: (a, b) if a <= b else (b, a),
        _floats,
        _floats,
    ),
    interval=st.builds(
        lambda a, b: (a, b) if a <= b else (b, a),
        _floats,
        _floats,
    ),
)
@settings(**property_settings("test_clamp_is_monotonic_in_x"))
def test_clamp_is_monotonic_in_x(
    ordered_pair: tuple[float, float], interval: tuple[float, float]
) -> None:
    x1, x2 = ordered_pair
    lo, hi = interval

    first = clamp(x1, lo, hi)
    second = clamp(x2, lo, hi)
    regression_note(
        "clamp_monotonic",
        {"x1": x1, "x2": x2, "lo": lo, "hi": hi, "first": first, "second": second},
    )

    assert first <= second + 1e-12


@given(
    prev=_floats, value=_floats, alpha=st.floats(min_value=0.0, max_value=1.0, width=64)
)
@settings(**property_settings("test_ema_is_convex_combination"))
def test_ema_is_convex_combination(prev: float, value: float, alpha: float) -> None:
    result = ema(prev, value, alpha)
    regression_note(
        "ema_convex",
        {"prev": prev, "value": value, "alpha": alpha, "result": result},
    )

    lo = min(prev, value)
    hi = max(prev, value)
    # allow small floating slop for extremal rounding when prev/value are large
    tolerance = max(1.0, abs(lo), abs(hi)) * 1e-12
    if result < lo:
        assert math.isclose(result, lo, rel_tol=0.0, abs_tol=tolerance)
    elif result > hi:
        assert math.isclose(result, hi, rel_tol=0.0, abs_tol=tolerance)
    else:
        assert lo <= result <= hi

    if alpha == 0.0:
        assert result == pytest.approx(prev)
    if alpha == 1.0:
        assert result == pytest.approx(value)


@given(
    prev=_floats,
    value=_floats,
    alpha=st.floats(min_value=0.0, max_value=1.0, width=64),
    offset=_floats,
)
@settings(**property_settings("test_ema_translation_invariance"))
def test_ema_translation_invariance(
    prev: float, value: float, alpha: float, offset: float
) -> None:
    baseline = ema(prev, value, alpha)
    shifted = ema(prev + offset, value + offset, alpha)
    regression_note(
        "ema_translate",
        {
            "prev": prev,
            "value": value,
            "alpha": alpha,
            "offset": offset,
            "baseline": baseline,
            "shifted": shifted,
        },
    )

    assert shifted == pytest.approx(baseline + offset)
