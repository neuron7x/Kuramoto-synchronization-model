# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np

from rl.replay.sleep_engine import SleepReplayEngine, Transition


def test_sleep_replay_priority_and_sampling():
    engine = SleepReplayEngine()
    state = np.zeros(3)
    action = np.zeros(2)
    next_state = np.zeros(3)
    priority = engine.observe_transition(
        state,
        action,
        0.1,
        next_state,
        td_error=0.5,
        cp_score=1.0,
        imminence_jump=0.5,
    )
    assert priority > 0.5
    state[...] = 5.0
    next_state[...] = -3.0
    batch = engine.sample(batch_size=1)
    assert isinstance(batch, list)
    stored = batch[0]
    assert np.all(stored.state == 0)
    assert np.all(stored.next_state == 0)


def test_sleep_replay_zero_priority_fallback():
    engine = SleepReplayEngine()
    for _ in range(10):
        engine.observe_transition(
            np.ones(2),
            np.ones(2),
            reward=0.0,
            next_state=np.ones(2),
            td_error=0.0,
        )
    batch = engine.sample(batch_size=5)
    assert len(batch) == 5


def test_sleep_replay_generator_contract():
    engine = SleepReplayEngine()

    class DummyGenerator:
        def __init__(self) -> None:
            self.calls = 0

        def sample(self, m: int):
            self.calls += 1
            return [(np.zeros(1),) * 4 for _ in range(m)]

    generator = DummyGenerator()
    batch = engine.dgr_batch(generator, 3)
    assert len(batch) == 3
    assert generator.calls == 1


def test_sleep_replay_sample_allows_small_buffers():
    engine = SleepReplayEngine()
    for i in range(3):
        engine.observe_transition(
            np.full(2, i, dtype=float),
            np.zeros(1),
            reward=0.0,
            next_state=np.full(2, i + 1, dtype=float),
            td_error=0.1,
        )

    batch = engine.sample(batch_size=5)
    assert len(batch) == 5
    for transition in batch:
        assert isinstance(transition, Transition)
