import numpy as np

from analytics.signals.irreversibility import ZScoreQuantizer


def test_zscore_quantizer_monotonic_states():
    quantizer = ZScoreQuantizer(window=10, n_states=7)
    xs = np.linspace(-3, 3, 50)
    states = [quantizer.update_and_state(float(x)) for x in xs]

    inversions = sum(1 for i in range(1, len(states)) if states[i] < states[i - 1] - 1)
    assert inversions == 0
