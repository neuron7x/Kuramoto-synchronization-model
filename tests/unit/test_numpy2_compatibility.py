import numpy as np
import pytest

from core.indicators.kuramoto import compute_phase, kuramoto_order


def test_compute_phase_no_copy_warning():
    data = np.random.randn(256)
    with pytest.warns(None) as caught:
        result = compute_phase(data)
    assert result.shape == data.shape
    for warning in caught:
        assert "copy" not in str(warning.message).lower()


def test_kuramoto_order_fast_path():
    phases = np.linspace(-np.pi, np.pi, 64)
    value = kuramoto_order(phases)
    assert 0.0 <= float(value) <= 1.0
