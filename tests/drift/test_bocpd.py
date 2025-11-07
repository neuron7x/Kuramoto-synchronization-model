from __future__ import annotations

from core.drift.bocpd import BOCPD


def test_bocpd_run_length_reset() -> None:
    detector = BOCPD(hazard=0.0, z_limit=1.5)
    run_lengths = []
    for value in [0.0] * 20:
        run_lengths.append(detector.update(value))
    pre_change = run_lengths[-1]
    post = detector.update(5.0)
    assert post == 0
    assert pre_change > post
