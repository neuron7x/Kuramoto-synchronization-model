import numpy as np

from core.metrics.holder import _Q_ZERO_THRESHOLD, _clamp_q_values


def test_clamp_q_values_preserves_sign_and_threshold():
    q_values = np.array([-0.001, -1e-6, 0.0, 1e-6, 0.5])

    clamped = _clamp_q_values(q_values)

    assert clamped[0] == -_Q_ZERO_THRESHOLD
    assert clamped[1] == -_Q_ZERO_THRESHOLD
    assert clamped[2] == _Q_ZERO_THRESHOLD
    assert clamped[3] == _Q_ZERO_THRESHOLD
    assert clamped[4] == 0.5
