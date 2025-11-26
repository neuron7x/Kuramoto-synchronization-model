"""Tests for dopamine numerical invariants and safety checks."""

from __future__ import annotations

import pytest

try:
    from hypothesis import given
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

    # Dummy decorators for when hypothesis is not available
    def given(*args, **kwargs):
        return lambda f: pytest.mark.skip(reason="hypothesis not installed")(f)

    class st:
        @staticmethod
        def floats(*args, **kwargs):
            return None


from tradepulse.core.neuro.dopamine._invariants import (
    assert_no_nan_inf,
    check_monotonic_thresholds,
    clamp,
    ensure_finite,
    rate_limited_change,
    validate_positive,
    validate_probability,
)


class TestAssertNoNanInf:
    """Tests for NaN/Inf assertion."""

    def test_accepts_finite_values(self) -> None:
        """Should pass for finite values."""
        assert_no_nan_inf(0.0, 1.0, -1.0, 1e-10, 1e10)

    def test_rejects_nan(self) -> None:
        """Should raise RuntimeError for NaN."""
        with pytest.raises(RuntimeError, match="NaN or ±Inf"):
            assert_no_nan_inf(1.0, float("nan"), 2.0)

    def test_rejects_inf(self) -> None:
        """Should raise RuntimeError for +Inf."""
        with pytest.raises(RuntimeError, match="NaN or ±Inf"):
            assert_no_nan_inf(1.0, float("inf"))

    def test_rejects_neg_inf(self) -> None:
        """Should raise RuntimeError for -Inf."""
        with pytest.raises(RuntimeError, match="NaN or ±Inf"):
            assert_no_nan_inf(float("-inf"), 0.0)

    def test_includes_context_in_error(self) -> None:
        """Should include context dict in error message."""
        context = {"param": "test", "value": 42}
        with pytest.raises(RuntimeError, match="Context:.*test"):
            assert_no_nan_inf(float("nan"), context=context)


class TestClamp:
    """Tests for clamp utility."""

    def test_clamps_below_minimum(self) -> None:
        """Should clamp values below minimum."""
        assert clamp(-5.0, 0.0, 10.0) == 0.0

    def test_clamps_above_maximum(self) -> None:
        """Should clamp values above maximum."""
        assert clamp(15.0, 0.0, 10.0) == 10.0

    def test_passes_values_in_range(self) -> None:
        """Should pass through values within range."""
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_handles_boundaries(self) -> None:
        """Should handle boundary values correctly."""
        assert clamp(0.0, 0.0, 10.0) == 0.0
        assert clamp(10.0, 0.0, 10.0) == 10.0

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        value=st.floats(
            min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
        ),
        min_val=st.floats(
            min_value=-1e3, max_value=0.0, allow_nan=False, allow_infinity=False
        ),
        max_val=st.floats(
            min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False
        ),
    )
    def test_clamp_property_always_in_range(
        self, value: float, min_val: float, max_val: float
    ) -> None:
        """Property: clamped value should always be in [min_val, max_val]."""
        result = clamp(value, min_val, max_val)
        assert min_val <= result <= max_val


class TestEnsureFinite:
    """Tests for ensure_finite validator."""

    def test_accepts_finite_values(self) -> None:
        """Should accept finite values."""
        assert ensure_finite("test", 1.0) == 1.0
        assert ensure_finite("test", -1.0) == -1.0
        assert ensure_finite("test", 0.0) == 0.0

    def test_rejects_nan(self) -> None:
        """Should raise ValueError for NaN."""
        with pytest.raises(ValueError, match="must be a finite number"):
            ensure_finite("test_param", float("nan"))

    def test_rejects_inf(self) -> None:
        """Should raise ValueError for infinity."""
        with pytest.raises(ValueError, match="must be a finite number"):
            ensure_finite("test_param", float("inf"))


class TestValidateProbability:
    """Tests for probability validation."""

    def test_accepts_valid_probabilities(self) -> None:
        """Should accept probabilities in [0, 1]."""
        assert validate_probability("p", 0.0) == 0.0
        assert validate_probability("p", 0.5) == 0.5
        assert validate_probability("p", 1.0) == 1.0

    def test_rejects_negative(self) -> None:
        """Should reject negative values."""
        with pytest.raises(ValueError, match="must be in \\[0, 1\\]"):
            validate_probability("p", -0.1)

    def test_rejects_above_one(self) -> None:
        """Should reject values > 1."""
        with pytest.raises(ValueError, match="must be in \\[0, 1\\]"):
            validate_probability("p", 1.1)

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        p=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    )
    def test_probability_property(self, p: float) -> None:
        """Property: valid probabilities should pass validation."""
        result = validate_probability("p", p)
        assert 0.0 <= result <= 1.0


class TestValidatePositive:
    """Tests for positive value validation."""

    def test_accepts_positive_values(self) -> None:
        """Should accept positive values."""
        assert validate_positive("x", 0.1) == 0.1
        assert validate_positive("x", 1.0) == 1.0

    def test_rejects_negative(self) -> None:
        """Should reject negative values."""
        with pytest.raises(ValueError, match="must be > 0"):
            validate_positive("x", -0.1)

    def test_rejects_zero_by_default(self) -> None:
        """Should reject zero by default."""
        with pytest.raises(ValueError, match="must be > 0"):
            validate_positive("x", 0.0)

    def test_accepts_zero_when_allowed(self) -> None:
        """Should accept zero when allow_zero=True."""
        assert validate_positive("x", 0.0, allow_zero=True) == 0.0

    def test_rejects_negative_even_with_allow_zero(self) -> None:
        """Should reject negative even with allow_zero=True."""
        with pytest.raises(ValueError, match="must be >= 0"):
            validate_positive("x", -0.1, allow_zero=True)


@pytest.mark.monotonic
class TestCheckMonotonicThresholds:
    """Tests for monotonic threshold enforcement."""

    def test_preserves_valid_monotonic_thresholds(self) -> None:
        """Should preserve thresholds that already satisfy go >= hold >= no_go."""
        go, hold, no_go = check_monotonic_thresholds(0.8, 0.5, 0.2)
        assert go == pytest.approx(0.8)
        assert hold == pytest.approx(0.5)
        assert no_go == pytest.approx(0.2)

    def test_fixes_go_less_than_hold(self) -> None:
        """Should adjust when go < hold by sorting."""
        go, hold, no_go = check_monotonic_thresholds(0.3, 0.7, 0.1)
        assert go >= hold
        assert hold >= no_go
        # After sorting: [0.7, 0.3, 0.1]
        assert go == pytest.approx(0.7)
        assert hold == pytest.approx(0.3)
        assert no_go == pytest.approx(0.1)

    def test_fixes_hold_less_than_no_go(self) -> None:
        """Should adjust when hold < no_go by sorting."""
        go, hold, no_go = check_monotonic_thresholds(0.8, 0.2, 0.6)
        assert go >= hold
        assert hold >= no_go
        # After sorting: [0.8, 0.6, 0.2]
        assert go == pytest.approx(0.8)
        assert hold == pytest.approx(0.6)
        assert no_go == pytest.approx(0.2)

    def test_clamps_to_valid_range(self) -> None:
        """Should clamp all values to [0, 1]."""
        go, hold, no_go = check_monotonic_thresholds(1.5, 0.5, -0.5)
        assert 0.0 <= go <= 1.0
        assert 0.0 <= hold <= 1.0
        assert 0.0 <= no_go <= 1.0

    def test_all_equal_case(self) -> None:
        """Should handle case where all thresholds are equal."""
        go, hold, no_go = check_monotonic_thresholds(0.5, 0.5, 0.5)
        assert go == pytest.approx(0.5)
        assert hold == pytest.approx(0.5)
        assert no_go == pytest.approx(0.5)

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        go=st.floats(
            min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False
        ),
        hold=st.floats(
            min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False
        ),
        no_go=st.floats(
            min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_monotonic_property(self, go: float, hold: float, no_go: float) -> None:
        """Property: output should always satisfy go >= hold >= no_go and be in [0, 1]."""
        go_out, hold_out, no_go_out = check_monotonic_thresholds(go, hold, no_go)

        # All in valid range
        assert 0.0 <= go_out <= 1.0
        assert 0.0 <= hold_out <= 1.0
        assert 0.0 <= no_go_out <= 1.0

        # Monotonic constraint
        assert go_out >= hold_out - 1e-9  # Small epsilon for floating point
        assert hold_out >= no_go_out - 1e-9


class TestRateLimitedChange:
    """Tests for rate-limited parameter changes."""

    def test_allows_small_changes(self) -> None:
        """Should allow changes within rate limit."""
        result = rate_limited_change(1.0, 1.5, max_rate=1.0)
        assert result == pytest.approx(1.5)

    def test_limits_large_positive_changes(self) -> None:
        """Should limit large positive changes."""
        result = rate_limited_change(1.0, 5.0, max_rate=1.0)
        assert result == pytest.approx(2.0)

    def test_limits_large_negative_changes(self) -> None:
        """Should limit large negative changes."""
        result = rate_limited_change(5.0, 1.0, max_rate=1.0)
        assert result == pytest.approx(4.0)

    def test_respects_time_step(self) -> None:
        """Should scale rate limit by time step."""
        result = rate_limited_change(1.0, 5.0, max_rate=1.0, dt=2.0)
        assert result == pytest.approx(3.0)  # 1.0 + 1.0*2.0

    def test_zero_change(self) -> None:
        """Should handle zero change."""
        result = rate_limited_change(1.0, 1.0, max_rate=1.0)
        assert result == pytest.approx(1.0)

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        current=st.floats(
            min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
        target=st.floats(
            min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
        max_rate=st.floats(
            min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_rate_limit_property(
        self, current: float, target: float, max_rate: float
    ) -> None:
        """Property: change should never exceed max_rate (for dt=1)."""
        result = rate_limited_change(current, target, max_rate, dt=1.0)
        actual_change = abs(result - current)
        assert actual_change <= max_rate + 1e-9  # Small epsilon for floating point
