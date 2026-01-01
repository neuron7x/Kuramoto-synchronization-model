# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import numpy as np

from rl.replay.sleep_engine import SleepReplayEngine


def test_sleep_replay_handles_invalid_td_error() -> None:
    engine = SleepReplayEngine()
    engine.observe_transition(
        np.zeros(2),
        np.zeros(1),
        reward=0.0,
        next_state=np.ones(2),
        td_error=float("nan"),
    )
    engine.observe_transition(
        np.ones(2),
        np.ones(1),
        reward=0.0,
        next_state=np.ones(2),
        td_error=float("inf"),
    )

    batch = engine.sample(batch_size=2)

    assert len(batch) == 2
