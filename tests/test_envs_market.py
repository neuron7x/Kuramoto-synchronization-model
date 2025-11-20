import numpy as np

from envs.market_env import RegimeShiftEnv, ToyMarketEnv, _max_drawdown


def test_toy_market_step_shapes():
    env = ToyMarketEnv(dim_state=16, dim_action=4)
    state = env.reset()
    assert state.shape == (16,)
    action = np.zeros(4, dtype=np.float32)
    reward, next_state, info = env.step(action)
    assert isinstance(reward, float)
    assert next_state.shape == (16,)
    expected_keys = {
        "latent",
        "maxdd",
        "volshock",
        "cp",
        "exp_ret",
        "novelty",
        "load",
        "fd",
    }
    assert expected_keys <= info.keys()
    expected_maxdd = _max_drawdown(np.array(env.returns, dtype=float))
    assert np.isclose(info["maxdd"], expected_maxdd)


def test_toy_market_deterministic_rng():
    seed = 42
    env_a = ToyMarketEnv(dim_state=8, dim_action=2, rng=np.random.default_rng(seed))
    env_b = ToyMarketEnv(dim_state=8, dim_action=2, rng=np.random.default_rng(seed))
    action = np.zeros(2, dtype=np.float32)
    env_a.reset()
    env_b.reset()

    for _ in range(5):
        reward_a, state_a, info_a = env_a.step(action)
        reward_b, state_b, info_b = env_b.step(action)
        assert reward_a == reward_b
        np.testing.assert_allclose(state_a, state_b)
        assert info_a.keys() == info_b.keys()
        for key in info_a:
            assert np.isclose(info_a[key], info_b[key])
        expected_a = _max_drawdown(np.array(env_a.returns, dtype=float))
        expected_b = _max_drawdown(np.array(env_b.returns, dtype=float))
        assert np.isclose(info_a["maxdd"], expected_a)
        assert np.isclose(info_b["maxdd"], expected_b)


def test_regime_shift_switching():
    env = RegimeShiftEnv(dim_state=8, dim_action=2, T=100, rng=np.random.default_rng(7))
    env.reset()
    rewards = []
    for _ in range(10):
        reward, _, _ = env.step(np.zeros(2, dtype=np.float32))
        rewards.append(reward)
    assert len(rewards) == 10


def test_max_drawdown_helper():
    returns = np.array([0.1, -0.2, 0.05, -0.1], dtype=float)
    assert np.isclose(_max_drawdown(returns), 0.25)
    assert _max_drawdown(np.array([], dtype=float)) == 0.0
