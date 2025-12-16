# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Property tests for MLSDM metrics using Hypothesis.

These property tests verify numerical invariants across a wide range
of randomly generated inputs:
- Finite vectors always produce finite outputs
- Vectors with injected NaN/Inf are properly rejected in strict mode
"""

from __future__ import annotations

import numpy as np
import pytest

try:
    from hypothesis import given, settings, strategies as st
    from hypothesis.extra.numpy import arrays

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

try:
    from tradepulse.sdk.mlsdm.memory.multi_level_memory import (
        MultiLevelSynapticMemory,
    )
    from tradepulse.sdk.mlsdm.utils.coherence_safety_metrics import (
        cosine_coherence,
        memory_coherence,
        safety_score,
        temporal_coherence,
    )
    from tradepulse.sdk.mlsdm.utils.input_validator import NumericalContractError
except ImportError:
    from src.tradepulse.sdk.mlsdm.memory.multi_level_memory import (
        MultiLevelSynapticMemory,
    )
    from src.tradepulse.sdk.mlsdm.utils.coherence_safety_metrics import (
        cosine_coherence,
        memory_coherence,
        safety_score,
        temporal_coherence,
    )
    from src.tradepulse.sdk.mlsdm.utils.input_validator import NumericalContractError


pytestmark = pytest.mark.skipif(
    not HAS_HYPOTHESIS, reason="hypothesis not installed"
)


# Hypothesis settings for determinism and reasonable test duration
HYPOTHESIS_SETTINGS = settings(
    max_examples=100,
    deadline=None,  # Disable deadline for slow operations
    derandomize=True,  # Use deterministic examples for reproducibility
)


# ============================================================================
# Strategies for generating test data
# ============================================================================


def finite_float_arrays(
    shape: tuple[int, ...] | int,
    dtype: type = np.float64,
) -> st.SearchStrategy[np.ndarray]:
    """Strategy for generating finite float arrays."""
    if isinstance(shape, int):
        shape = (shape,)
    return arrays(
        dtype=dtype,
        shape=shape,
        elements=st.floats(
            min_value=-1e6,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        ),
    )


def arrays_with_nan_or_inf(
    shape: tuple[int, ...] | int,
) -> st.SearchStrategy[np.ndarray]:
    """Strategy for generating arrays that definitely contain NaN or Inf."""
    if isinstance(shape, int):
        shape = (shape,)

    def inject_nan_inf(arr: np.ndarray) -> np.ndarray:
        arr = arr.copy()
        idx = np.random.default_rng(42).integers(0, arr.size)
        flat = arr.flatten()
        flat[idx] = np.random.default_rng(42).choice([np.nan, np.inf, -np.inf])
        return flat.reshape(arr.shape)

    return arrays(
        dtype=np.float64,
        shape=shape,
        elements=st.floats(
            min_value=-1e6,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        ),
    ).map(inject_nan_inf)


# ============================================================================
# Property tests for coherence metrics
# ============================================================================


@HYPOTHESIS_SETTINGS
@given(
    vec_a=finite_float_arrays(10),
    vec_b=finite_float_arrays(10),
)
def test_cosine_coherence_finite_inputs_produce_finite_output(
    vec_a: np.ndarray, vec_b: np.ndarray
) -> None:
    """Cosine coherence with finite inputs always produces finite output in [0,1]."""
    result = cosine_coherence(vec_a, vec_b)
    assert np.isfinite(result), f"Result {result} is not finite"
    assert 0.0 <= result <= 1.0, f"Result {result} not in [0, 1]"


@HYPOTHESIS_SETTINGS
@given(
    vec=finite_float_arrays(10),
    ref=finite_float_arrays(10),
)
def test_safety_score_finite_inputs_produce_finite_output(
    vec: np.ndarray, ref: np.ndarray
) -> None:
    """Safety score with finite inputs always produces finite output in [0,1]."""
    result = safety_score(vec, ref)
    assert np.isfinite(result), f"Result {result} is not finite"
    assert 0.0 <= result <= 1.0, f"Result {result} not in [0, 1]"


@HYPOTHESIS_SETTINGS
@given(
    l1=finite_float_arrays(10),
    l2=finite_float_arrays(10),
    l3=finite_float_arrays(10),
)
def test_memory_coherence_finite_inputs_produce_finite_output(
    l1: np.ndarray, l2: np.ndarray, l3: np.ndarray
) -> None:
    """Memory coherence with finite inputs always produces finite output in [0,1]."""
    result = memory_coherence(l1, l2, l3)
    assert np.isfinite(result), f"Result {result} is not finite"
    assert 0.0 <= result <= 1.0, f"Result {result} not in [0, 1]"


@HYPOTHESIS_SETTINGS
@given(
    window_size=st.integers(min_value=0, max_value=20),
    vec_dim=st.integers(min_value=1, max_value=10),
)
def test_temporal_coherence_finite_window_produces_finite_output(
    window_size: int, vec_dim: int
) -> None:
    """Temporal coherence with finite window always produces finite output in [0,1]."""
    rng = np.random.default_rng(42)
    window = [rng.standard_normal(vec_dim) for _ in range(window_size)]
    result = temporal_coherence(window)
    assert np.isfinite(result), f"Result {result} is not finite"
    assert 0.0 <= result <= 1.0, f"Result {result} not in [0, 1]"


# ============================================================================
# Property tests for strict mode behavior
# ============================================================================


@HYPOTHESIS_SETTINGS
@given(vec=arrays_with_nan_or_inf(10))
def test_cosine_coherence_rejects_nan_inf_strict_mode(vec: np.ndarray) -> None:
    """Cosine coherence in strict mode consistently raises on NaN/Inf."""
    ref = np.ones(10)
    with pytest.raises(NumericalContractError):
        cosine_coherence(vec, ref, strict_mode=True)


@HYPOTHESIS_SETTINGS
@given(vec=arrays_with_nan_or_inf(10))
def test_safety_score_rejects_nan_inf_strict_mode(vec: np.ndarray) -> None:
    """Safety score in strict mode consistently raises on NaN/Inf."""
    with pytest.raises(NumericalContractError):
        safety_score(vec, strict_mode=True)


# ============================================================================
# Property tests for MultiLevelSynapticMemory
# ============================================================================


@HYPOTHESIS_SETTINGS
@given(event=finite_float_arrays(16))
def test_memory_update_finite_inputs_produce_finite_state(
    event: np.ndarray,
) -> None:
    """Memory update with finite inputs always produces finite state."""
    memory = MultiLevelSynapticMemory(dim=16, strict_mode=True)
    memory.update(event)

    state = memory.get_state()
    assert np.all(np.isfinite(state.l1)), "L1 contains non-finite values"
    assert np.all(np.isfinite(state.l2)), "L2 contains non-finite values"
    assert np.all(np.isfinite(state.l3)), "L3 contains non-finite values"


@HYPOTHESIS_SETTINGS
@given(event=arrays_with_nan_or_inf(16))
def test_memory_update_rejects_nan_inf_strict_mode(event: np.ndarray) -> None:
    """Memory update in strict mode consistently raises on NaN/Inf."""
    memory = MultiLevelSynapticMemory(dim=16, strict_mode=True)
    with pytest.raises(NumericalContractError):
        memory.update(event)


@HYPOTHESIS_SETTINGS
@given(event=arrays_with_nan_or_inf(16))
def test_memory_update_sanitizes_nan_inf_non_strict_mode(
    event: np.ndarray,
) -> None:
    """Memory update in non-strict mode sanitizes and produces finite state."""
    memory = MultiLevelSynapticMemory(dim=16, strict_mode=False)
    memory.update(event)  # Should not raise

    state = memory.get_state()
    assert np.all(np.isfinite(state.l1)), "L1 contains non-finite values after sanitization"
    assert np.all(np.isfinite(state.l2)), "L2 contains non-finite values after sanitization"
    assert np.all(np.isfinite(state.l3)), "L3 contains non-finite values after sanitization"


@HYPOTHESIS_SETTINGS
@given(
    lambda_l1=st.floats(min_value=0.01, max_value=1.0),
    lambda_l2=st.floats(min_value=0.01, max_value=1.0),
    lambda_l3=st.floats(min_value=0.01, max_value=1.0),
)
def test_memory_lambda_hierarchy_validation(
    lambda_l1: float, lambda_l2: float, lambda_l3: float
) -> None:
    """Memory correctly validates λ hierarchy: λ3 <= λ2 <= λ1."""
    hierarchy_valid = lambda_l3 <= lambda_l2 <= lambda_l1

    if hierarchy_valid:
        # Should succeed
        memory = MultiLevelSynapticMemory(
            dim=8,
            lambda_l1=lambda_l1,
            lambda_l2=lambda_l2,
            lambda_l3=lambda_l3,
        )
        assert memory.lambda_l1 == lambda_l1
    else:
        # Should raise
        with pytest.raises((ValueError, Exception)):
            MultiLevelSynapticMemory(
                dim=8,
                lambda_l1=lambda_l1,
                lambda_l2=lambda_l2,
                lambda_l3=lambda_l3,
            )


# ============================================================================
# Edge case property tests
# ============================================================================


@HYPOTHESIS_SETTINGS
@given(
    scale=st.floats(min_value=1e-10, max_value=1e10),
)
def test_cosine_coherence_scale_invariant(scale: float) -> None:
    """Cosine coherence is scale-invariant."""
    rng = np.random.default_rng(42)
    vec = rng.standard_normal(10)

    result_original = cosine_coherence(vec, vec)
    result_scaled = cosine_coherence(vec * scale, vec * scale)

    assert result_original == pytest.approx(result_scaled, rel=1e-6)


@HYPOTHESIS_SETTINGS
@given(
    dim=st.integers(min_value=1, max_value=100),
)
def test_zero_vector_coherence_is_05(dim: int) -> None:
    """Zero vectors always produce 0.5 coherence (neutral)."""
    zero = np.zeros(dim)
    nonzero = np.ones(dim)

    result = cosine_coherence(zero, nonzero)
    assert result == pytest.approx(0.5)

    result_both_zero = cosine_coherence(zero, zero)
    assert result_both_zero == pytest.approx(0.5)
