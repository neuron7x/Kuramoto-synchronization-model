import numpy as np

from core.metrics.aperiodic import aperiodic_slope
from core.metrics.dfa import dfa_alpha
from core.metrics.fractal_dimension import box_counting_dim
from utils.fractal_cascade import DyadicPMCascade, pink_noise


def test_metrics_fractal_properties():
    signal = pink_noise(4_096, beta=1.0)
    alpha = dfa_alpha(signal, min_win=50, max_win=1_000, n_win=8)
    assert alpha > 0.2

    slope = aperiodic_slope(signal, fs=100)
    assert slope < -0.1

    dimension = box_counting_dim(signal)
    assert dimension > 0.5


def test_dyadic_cascade_adjustment_bounds():
    cascade = DyadicPMCascade(depth=4, p=0.55, heavy_tail=0.4, base_dt=30.0)
    samples = cascade.sample(16)
    assert samples.shape == (16,)
    cascade.adjust_heavy_tail(1.0)
    assert 0.0 <= cascade.heavy_tail <= 1.0
    cascade.adjust_heavy_tail(-2.0)
    assert 0.0 <= cascade.heavy_tail <= 1.0
    with np.testing.assert_raises(ValueError):
        DyadicPMCascade(depth=-1)


def test_pink_noise_invalid_length():
    with np.testing.assert_raises(ValueError):
        pink_noise(0)
