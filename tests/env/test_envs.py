from __future__ import annotations

from core.env.hawkes_env import HawkesConfig, HawkesEnv
from core.env.nhp_env import NHPConfig, NHPEnv


def test_env_smokes() -> None:
    hawkes = HawkesEnv(HawkesConfig(mu=0.5, alpha=0.8, beta=1.5, num_steps=20))
    obs = hawkes.reset()
    for _ in range(10):
        obs, reward, done = hawkes.step(1)
    nhp = NHPEnv(NHPConfig(hidden_size=4, num_steps=20, baseline_intensity=0.3))
    obs = nhp.reset()
    for _ in range(10):
        obs, reward, done = nhp.step(1)
