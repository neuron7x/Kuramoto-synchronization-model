import numpy as np

from rl.replay.sleep_engine import SleepReplayEngine


def test_sleep_replay_priority_and_sampling():
    engine = SleepReplayEngine()
    priority = engine.observe_transition(
        np.zeros(3),
        np.zeros(2),
        0.1,
        np.zeros(3),
        td_error=0.5,
        cp_score=1.0,
        imminence_jump=0.5,
    )
    assert priority > 0.5
    batch = engine.sample(batch_size=1)
    assert isinstance(batch, list)
