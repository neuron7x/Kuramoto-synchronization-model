import numpy as np

from core.metrics.aperiodic import aperiodic_slope
from core.metrics.dfa import dfa_alpha
from core.metrics.fractal_dimension import box_counting_dim
from utils.fractal_cascade import pink_noise


def test_metrics_fractal_properties():
    signal = pink_noise(4_096, beta=1.0)
    alpha = dfa_alpha(signal, min_win=50, max_win=1_000, n_win=8)
    assert alpha > 0.2

    slope = aperiodic_slope(signal, fs=100)
    assert slope < -0.1

    dimension = box_counting_dim(signal)
    assert dimension > 0.5
