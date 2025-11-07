from __future__ import annotations

import numpy as np

from core.replay.per import PERBuffer


def test_sampling_bias_and_breach() -> None:
    buf = PERBuffer(capacity=10, alpha=0.6, beta=0.4, eps=1e-3)
    buf.configure_breach(3.0)
    transition = (np.zeros(4), 0, 0.0, np.zeros(4), False)
    buf.add(transition, priority=1.0)
    buf.add(transition, priority=5.0)
    buf.add(transition, priority=1.0)
    counts = {0: 0, 1: 0, 2: 0}
    for _ in range(1000):
        idxs, *_ = buf.sample(1)
        counts[idxs[0]] += 1
    assert counts[1] > counts[0]
    buf.mark_recent(2)
    buf.update_priorities([1, 2], np.array([1.0, 1.0]))
    assert buf.priorities[2] > buf.priorities[0]
