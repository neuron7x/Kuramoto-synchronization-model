import numpy as np
import pytest

try:
    import torch  # noqa: F401
    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - torch import failure is a skip condition
    TORCH_AVAILABLE = False

from runtime.misanthropic_agent import MisanthropicAgent


class HawkesEnv:
    """Lightweight Hawkes-like environment to exercise agent training."""

    def __init__(self, mu: float = 0.5, alpha: float = 0.8, beta: float = 1.5, num_steps: int = 300) -> None:
        self.mu = mu
        self.alpha = alpha
        self.beta = beta
        self.num_steps = num_steps
        self.price = 100.0
        self.t = 0.0
        self.event_times: list[float] = []
        self.iteration = 0

    def reset(self):
        self.price = 100.0
        self.t = 0.0
        self.event_times = []
        self.iteration = 0
        return self._state()

    def step(self, action: int):
        self.iteration += 1
        intensity = self.mu + self.alpha * sum(np.exp(-self.beta * (self.t - s)) for s in self.event_times if s < self.t)
        intensity = max(intensity, 1e-6)
        dt = -np.log(max(1e-12, np.random.uniform())) / intensity
        self.t += dt
        if np.random.uniform() < min(0.99, intensity / (intensity + self.mu + 1e-6)):
            self.event_times.append(self.t)

        shock = np.random.normal(0, 0.05)
        drift = 0.02 * (1 if action == 0 else -1 if action == 1 else 0)
        self.price += drift + shock
        reward = drift + shock
        done = self.iteration >= self.num_steps
        return self._state(), float(reward), bool(done)

    def _state(self):
        lob_data = {
            "delta_ask_vol": np.random.normal(0, 1, 10),
            "delta_bid_vol": np.random.normal(0, 1, 10),
            "depth": float(np.random.uniform(50, 150)),
            "rv": float(np.random.normal(0, 0.2)),
            "skew": float(np.random.uniform(-1, 1)),
        }
        return {"lob_data": lob_data, "price": float(self.price)}


def test_import_and_step():
    if not TORCH_AVAILABLE:
        pytest.skip("torch unavailable")

    agent = MisanthropicAgent()
    env = HawkesEnv(num_steps=10)
    state = env.reset()
    action, size = agent.step(state["lob_data"], state["price"])
    assert action in (0, 1, 2)
    assert np.isfinite(size)


def test_train_and_eval_smoke():
    if not TORCH_AVAILABLE:
        pytest.skip("torch unavailable")

    agent = MisanthropicAgent()
    env = HawkesEnv(num_steps=80)
    agent.batch_size = 16
    agent.train(env, episodes=2)

    stream = []
    state = env.reset()
    for _ in range(120):
        stream.append((state["lob_data"], state["price"]))
        state, _, _ = env.step(np.random.choice([0, 1, 2]))

    metrics = agent.evaluate_stream(stream)
    assert set(metrics) == {"pnl_mean", "cvar_95", "coverage", "r2_ofi"}
    assert np.isfinite(metrics["pnl_mean"])
    assert 0.0 <= metrics["coverage"] <= 1.0


def test_cvar_lagrangian_ablation():
    if not TORCH_AVAILABLE:
        pytest.skip("torch unavailable")

    env = HawkesEnv(num_steps=60)

    agent_with_cvar = MisanthropicAgent()
    agent_with_cvar.batch_size = 8
    agent_with_cvar.lambda_cvar = 1.0
    agent_with_cvar.train(env, episodes=1)
    metrics_cvar = agent_with_cvar.evaluate_stream(
        [(env._state()["lob_data"], env._state()["price"]) for _ in range(60)]
    )

    agent_without_cvar = MisanthropicAgent()
    agent_without_cvar.batch_size = 8
    agent_without_cvar.lambda_cvar = 0.0
    agent_without_cvar.train(env, episodes=1)
    metrics_plain = agent_without_cvar.evaluate_stream(
        [(env._state()["lob_data"], env._state()["price"]) for _ in range(60)]
    )

    assert metrics_cvar["cvar_95"] >= metrics_plain["cvar_95"]
