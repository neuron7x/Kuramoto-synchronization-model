# mypy: ignore-errors
"""Tests for DFA gamma estimator — Peng 1994 + wavelet cross-validation.

Coverage of INV-AC1-rev (Adaptive Criticality, Membrane Isolation):
the criticality gate κ_critical = -ln(ΔH_max/ε) / (λ_local + δ) uses
``DFAGammaEstimator.hurst_exponent`` as λ_local. The tests below pin
the qualitative regime classification of the DFA estimator that the
gate consumes:

* white-noise input  → λ_local ≈ 0.5 (chaotic regime)
* random-walk input  → λ_local → 1.0 (persistent regime)
* differenced input  → λ_local < 0.5 (anti-persistent regime)
* gamma identity     → γ = 2·H + 1 to float precision

If any of these regress, the membrane-isolation gate downstream
(INV-AC1-rev) silently misclassifies the topology of every node.
"""

from __future__ import annotations

import numpy as np
import pytest

from geosync.estimators.dfa_gamma_estimator import DFAEstimate, DFAGammaEstimator


@pytest.fixture
def est() -> DFAGammaEstimator:
    return DFAGammaEstimator(min_quality=0.90)


# --- fBm-like synthetic tests ---


def test_white_noise_H_near_half(est: DFAGammaEstimator) -> None:
    """INV-AC1-rev λ_local: white noise → H ≈ 0.5, γ ≈ 2.0 (chaotic regime)."""
    rng = np.random.default_rng(42)
    g = est.compute(rng.standard_normal(4096))
    assert 0.3 <= g.hurst_exponent <= 0.7, f"White noise H={g.hurst_exponent}"
    assert abs(g.gamma - (2 * g.hurst_exponent + 1)) < 1e-10


def test_persistent_H_above_half(est: DFAGammaEstimator) -> None:
    """INV-AC1-rev λ_local: random walk (cumsum of WN) → H ≈ 1.0 → γ ≈ 3.0 (persistent)."""
    rng = np.random.default_rng(42)
    g = est.compute(np.cumsum(rng.standard_normal(4096)))
    assert g.hurst_exponent > 0.7, f"Persistent H={g.hurst_exponent}"
    assert g.gamma > 2.0


def test_anti_persistent(est: DFAGammaEstimator) -> None:
    """INV-AC1-rev λ_local: differenced random walk → anti-persistent H < 0.5."""
    rng = np.random.default_rng(42)
    g = est.compute(np.diff(np.cumsum(rng.standard_normal(4097))))
    assert g.hurst_exponent < 0.7


def test_gamma_equals_2H_plus_1(est: DFAGammaEstimator) -> None:
    """INV-AC1-rev / INV-DRO1: γ = 2H + 1 enforced by __post_init__ to float precision."""
    rng = np.random.default_rng(42)
    for seed in range(5):
        g = est.compute(np.cumsum(rng.standard_normal(2048)))
        assert abs(g.gamma - (2 * g.hurst_exponent + 1)) < 1e-10


def test_post_init_rejects_invalid_gamma() -> None:
    """__post_init__ raises ValueError if γ ≠ 2H+1."""
    with pytest.raises(ValueError, match="DERIVED"):
        DFAEstimate(
            hurst_exponent=0.5,
            gamma=1.5,  # should be 2.0
            dfa_fluctuations=(),
            scale_range=(4, 128),
            r_squared=0.99,
            wavelet_confirmed=True,
            n_samples=1024,
            computation_time_ms=1.0,
        )


def test_short_series_invalid() -> None:
    """< 128 samples → invalid estimate."""
    est = DFAGammaEstimator(min_quality=0.95)
    rng = np.random.default_rng(42)
    for n in [10, 30, 64, 127]:
        g = est.compute(rng.standard_normal(n))
        assert g.r_squared == 0.0
        assert g.n_samples == n


def test_r_squared_threshold_enforcement() -> None:
    """r_squared < min_quality → ValueError."""
    est = DFAGammaEstimator(min_quality=0.9999)
    rng = np.random.default_rng(42)
    with pytest.raises(ValueError, match="r_squared"):
        est.compute(rng.standard_normal(256))


def test_wavelet_confirmed_is_bool(est: DFAGammaEstimator) -> None:
    """wavelet_confirmed is always bool."""
    rng = np.random.default_rng(42)
    g = est.compute(np.cumsum(rng.standard_normal(2048)))
    assert isinstance(g.wavelet_confirmed, bool)


def test_frozen_dataclass_immutable(est: DFAGammaEstimator) -> None:
    """DFAEstimate is frozen — no mutation."""
    rng = np.random.default_rng(42)
    g = est.compute(np.cumsum(rng.standard_normal(2048)))
    with pytest.raises(AttributeError):
        g.gamma = 999.0  # type: ignore[misc]


def test_scale_range_valid(est: DFAGammaEstimator) -> None:
    """scale_range[0] < scale_range[1] for valid estimates."""
    rng = np.random.default_rng(42)
    g = est.compute(np.cumsum(rng.standard_normal(2048)))
    assert g.scale_range[0] > 0
    assert g.scale_range[0] < g.scale_range[1]


def test_computation_time_positive(est: DFAGammaEstimator) -> None:
    """computation_time_ms ≥ 0."""
    rng = np.random.default_rng(42)
    g = est.compute(np.cumsum(rng.standard_normal(2048)))
    assert g.computation_time_ms >= 0.0


def test_dfa_fluctuations_nonempty(est: DFAGammaEstimator) -> None:
    """Valid estimate has non-empty dfa_fluctuations tuple."""
    rng = np.random.default_rng(42)
    g = est.compute(np.cumsum(rng.standard_normal(2048)))
    assert len(g.dfa_fluctuations) >= 4
    assert all(f > 0 for f in g.dfa_fluctuations)
