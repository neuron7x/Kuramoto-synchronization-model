import numpy as np

from envs.market_env import ToyMarketEnv, RegimeShiftEnv


def test_toy_market_step_shapes():
    env = ToyMarketEnv(dim_state=16, dim_action=4)
    state = env.reset()
    assert state.shape == (16,)
    action = np.zeros(4, dtype=np.float32)
    reward, next_state, info = env.step(action)
    assert isinstance(reward, float)
    assert next_state.shape == (16,)
    expected_keys = {"latent", "maxdd", "volshock", "cp", "exp_ret", "novelty", "load", "fd"}
    assert expected_keys <= info.keys()


def test_regime_shift_switching():
    env = RegimeShiftEnv(dim_state=8, dim_action=2, T=100)
    env.reset()
    rewards = []
    for _ in range(10):
        reward, _, _ = env.step(np.zeros(2, dtype=np.float32))
        rewards.append(reward)
    assert len(rewards) == 10
