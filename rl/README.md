# RL (Reinforcement Learning) Module

## Overview

The `rl` module provides reinforcement learning infrastructure for developing and training RL-based trading agents.

## Purpose

- **RL Environments**: Trading environments compatible with Gym/Gymnasium
- **RL Agents**: Pre-trained and trainable RL agents
- **Training Infrastructure**: Distributed training and hyperparameter tuning
- **Evaluation**: Backtesting and evaluation of RL strategies

## Key Features

- 🤖 **Custom Environments**: Trading-specific RL environments
- 🧠 **Pre-trained Agents**: Ready-to-use RL agents
- 🎓 **Training Pipeline**: End-to-end training workflow
- 📊 **Evaluation Tools**: Comprehensive performance analysis
- 🔧 **Hyperparameter Tuning**: Automated optimization

## Technology Stack

- **Python**: 3.11+
- **Stable-Baselines3**: RL algorithms
- **Gymnasium**: Environment interface
- **Ray RLlib**: Distributed training (optional)
- **Optuna**: Hyperparameter optimization

## Usage Examples

### Trading Environment

```python
from rl import TradingEnvironment

# Create environment
env = TradingEnvironment(
    data=historical_data,
    initial_capital=100000,
    transaction_cost_bps=5
)

# Use with RL algorithm
obs, info = env.reset()

for _ in range(1000):
    action = agent.predict(obs)
    obs, reward, terminated, truncated, info = env.step(action)
    
    if terminated or truncated:
        obs, info = env.reset()
```

### Training Agent

```python
from rl import train_agent
from stable_baselines3 import PPO

# Train agent
agent = train_agent(
    algorithm=PPO,
    env=env,
    total_timesteps=1_000_000,
    eval_freq=10_000,
    save_path="models/ppo_agent"
)
```

### Evaluating Agent

```python
from rl import evaluate_agent

# Evaluate trained agent
results = evaluate_agent(
    agent=agent,
    env=test_env,
    n_episodes=100
)

print(f"Mean Return: {results.mean_return:.2f}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
```

## Configuration

```yaml
# config/rl.yaml
rl:
  environment:
    initial_capital: 100000
    transaction_cost_bps: 5
    max_position_pct: 0.2
    
  training:
    algorithm: PPO
    total_timesteps: 1000000
    learning_rate: 0.0003
    batch_size: 64
    
  evaluation:
    n_eval_episodes: 100
    deterministic: true
```

## Related Modules

- [`strategies`](../strategies/README.md): Trading strategies
- [`backtest`](../backtest/README.md): Backtesting
- [`core`](../core/README.md): Core infrastructure

## Documentation

- [RL Guide](https://docs.tradepulse.io/rl)
- [Training Guide](https://docs.tradepulse.io/rl/training)

## License

See [LICENSE](../LICENSE) for licensing information.
