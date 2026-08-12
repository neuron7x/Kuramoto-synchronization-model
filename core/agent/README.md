# Core Agent Module

## Overview

The `core.agent` module provides a comprehensive framework for managing, evaluating, and orchestrating trading strategies in the GeoSync platform. It includes multi-armed bandits, strategy evaluation, memory systems, orchestration, scheduling, and prompt management capabilities.

## Module Structure

```
core/agent/
├── __init__.py           # Module exports and public API
├── bandits.py            # Multi-armed bandit algorithms
├── evaluator.py          # Strategy batch evaluation
├── memory.py             # Strategy memory and adaptive learning
├── orchestrator.py       # Concurrent strategy orchestration
├── registry.py           # Agent registry
├── sandbox.py            # Sandboxed strategy execution
├── scheduler.py          # Job scheduling with cron support
├── strategy.py           # Strategy and PiAgent implementations
└── prompting/            # Prompt management subsystem
    ├── __init__.py
    ├── exceptions.py     # Custom exceptions
    ├── library.py        # Template library and experiments
    ├── manager.py        # High-level prompt management
    └── models.py         # Domain models
```

## Key Components

### 1. Multi-Armed Bandits (`bandits.py`)

Implements exploration-exploitation algorithms for strategy selection:

- **EpsilonGreedy**: Classic epsilon-greedy with cryptographically strong randomness
- **UCB1**: Upper Confidence Bound algorithm

```python
from core.agent.bandits import EpsilonGreedy, UCB1

# Epsilon-greedy bandit
bandit = EpsilonGreedy(
    arms=["strategy_a", "strategy_b", "strategy_c"],
    epsilon=0.1
)

# Select arm and update with reward
arm = bandit.select()
bandit.update(arm, reward=1.5)
estimate = bandit.estimate(arm)
```

### 2. Strategy Evaluation (`evaluator.py`)

High-throughput strategy evaluation with bounded concurrency:

```python
from core.agent import StrategyBatchEvaluator, Strategy, evaluate_strategies
import pandas as pd

# Create strategies
strategies = [
    Strategy(name="momentum", params={"lookback": 20}),
    Strategy(name="mean_reversion", params={"lookback": 50}),
]

# Prepare market data
data = pd.DataFrame({"close": [100, 101, 102, 103]})

# Evaluate strategies
evaluator = StrategyBatchEvaluator(max_workers=4)
results = evaluator.evaluate(strategies, data)

# Or use convenience function
results = evaluate_strategies(strategies, data, max_workers=4)
```

### 3. Strategy Memory (`memory.py`)

Episodic memory for caching successful strategies:

```python
from core.agent.memory import StrategyMemory, StrategySignature

memory = StrategyMemory(max_records=256)

# Store strategy with market signature
signature = StrategySignature(
    R=0.95,              # Ricci flow
    delta_H=0.05,        # Hurst exponent change
    kappa_mean=0.3,      # Mean curvature
    entropy=2.1,         # Market entropy
    instability=0.1      # Instability measure
)

memory.add("momentum_strategy", signature, score=0.85)

# Retrieve top performers
top_strategies = memory.topk(k=5)
```

### 4. Orchestration (`orchestrator.py`)

Coordinate parallel strategy evaluations:

```python
from core.agent import StrategyOrchestrator, StrategyFlow

orchestrator = StrategyOrchestrator(max_parallel=4)

# Create flows
flows = [
    StrategyFlow(
        name="flow_1",
        strategies=strategies_batch_1,
        dataset=data,
        priority=1
    ),
    StrategyFlow(
        name="flow_2", 
        strategies=strategies_batch_2,
        dataset=data,
        priority=2
    ),
]

# Execute flows concurrently
results = orchestrator.run_flows(flows)
```

### 5. Job Scheduling (`scheduler.py`)

Advanced scheduling with interval, cron, and event-based triggers:

```python
from core.agent import StrategyScheduler, StrategyJob

scheduler = StrategyScheduler()

# Interval-based job
job = StrategyJob(
    name="hourly_evaluation",
    strategies=strategies,
    data_provider=lambda: fetch_latest_data(),
    interval=3600,  # 1 hour
)

scheduler.add_job(job)
scheduler.start()  # Run in background

# Cron-based job
cron_job = StrategyJob(
    name="market_open",
    strategies=strategies,
    data_provider=data_source,
    cron="30 9 * * 1-5",  # 9:30 AM weekdays
)

scheduler.add_job(cron_job)

# Event-driven job
event_job = StrategyJob(
    name="volatility_spike",
    strategies=strategies,
    data_provider=data_source,
    event_triggers=["high_volatility", "market_crash"],
)

scheduler.add_job(event_job)
scheduler.trigger_event("high_volatility")
```

### 6. Sandboxing (`sandbox.py`)

Execute strategies in isolated, resource-governed subprocesses:

```python
from core.agent.sandbox import StrategySandbox, SandboxLimits

sandbox = StrategySandbox(
    limits=SandboxLimits(
        cpu_time_seconds=2.0,
        wall_time_seconds=5.0,
        memory_bytes=512 * 1024 * 1024,  # 512 MB
    )
)

result = sandbox.run(strategy, data, priority=0)
```

### 7. Agent Registry (`registry.py`)

Runtime registry for agent factories:

```python
from core.agent.registry import AgentRegistry, global_agent_registry

registry = global_agent_registry()

# Register custom agent
def my_agent_factory():
    return MyAgent()

registry.register("my_agent", my_agent_factory)

# Resolve agent
factory = registry.resolve("my_agent")
agent = factory()
```

### 8. Strategies and Agents (`strategy.py`)

Core strategy and agent implementations:

```python
from core.agent import Strategy, PiAgent

# Create strategy
strategy = Strategy(
    name="momentum",
    params={
        "lookback": 20,
        "threshold": 0.5,
        "risk_budget": 1.0,
    }
)

# Simulate performance
score = strategy.simulate_performance(data)

# Create PI agent with instability detection
agent = PiAgent(strategy=strategy, hysteresis=0.05)

market_state = {
    "R": 0.80,
    "delta_H": -0.05,
    "kappa_mean": -0.1,
    "transition_score": 0.3,
}

# Detect instability
if agent.detect_instability(market_state):
    print("Market instability detected!")
    
# Adaptive trading action
action = agent.evaluate_and_adapt(market_state)
```

### 9. Prompt Management (`prompting/`)

Template-based prompt management with experiments:

```python
from core.agent.prompting import (
    PromptManager,
    PromptTemplate,
    PromptTemplateLibrary,
    ParameterSpec,
)

# Create template
template = PromptTemplate(
    family="trading_signal",
    version="1.0",
    content="Generate signals for $symbol using $strategy approach",
    parameters=(
        ParameterSpec(name="symbol", required=True),
        ParameterSpec(name="strategy", required=True),
    ),
)

# Register and render
library = PromptTemplateLibrary()
library.register(template)

manager = PromptManager(library=library)
result = manager.render(
    "trading_signal",
    parameters={"symbol": "AAPL", "strategy": "momentum"},
)

print(result.prompt)
```

## Design Patterns

### 1. Resource Management
All components implement proper context managers and cleanup:

```python
with StrategyOrchestrator(max_parallel=4) as orchestrator:
    results = orchestrator.run_flows(flows)
# Automatically cleaned up
```

### 2. Error Handling
Comprehensive error handling with custom exceptions:

```python
from core.agent import StrategyEvaluationError, StrategyOrchestrationError

try:
    results = evaluator.evaluate(strategies, data, raise_on_error=True)
except StrategyEvaluationError as e:
    print(f"Failed strategies: {e.failures}")
```

### 3. Observable Metrics
Integration with observability stack:

```python
from core.utils.metrics import get_metrics_collector

collector = get_metrics_collector()
# Metrics automatically recorded during evaluation
```

### 4. Type Safety
Full type hints throughout:

```python
from typing import Sequence
from core.agent import Strategy, EvaluationResult

def evaluate(strategies: Sequence[Strategy]) -> list[EvaluationResult]:
    ...
```

## Testing

Run tests for the agent module:

```bash
pytest tests/core/agent/ -v
```

Run specific test categories:

```bash
# Bandits
pytest tests/core/agent/test_bandits.py -v

# Prompting
pytest tests/core/agent/test_prompt*.py -v

# Registry
pytest tests/core/agent/test_registry*.py -v
```

## Performance Considerations

1. **Concurrency**: Use appropriate `max_workers` based on CPU count
2. **Memory**: Configure sandbox limits to prevent resource exhaustion
3. **Caching**: Memory system caches strategy results for similar market conditions
4. **Batching**: Batch evaluator chunks work efficiently

## Security

- **Sandboxing**: Strategies run in isolated processes with resource limits
- **Prompt Injection**: Sanitizer detects and blocks malicious patterns
- **Input Validation**: All user inputs validated and sanitized

## API Reference

### Public Exports

```python
from core.agent import (
    # Evaluation
    EvaluationResult,
    StrategyBatchEvaluator,
    StrategyEvaluationError,
    evaluate_strategies,
    
    # Orchestration
    StrategyFlow,
    StrategyOrchestrationError,
    StrategyOrchestrator,
    
    # Scheduling
    StrategyJob,
    StrategyJobStatus,
    StrategyScheduler,
    
    # Strategies
    PiAgent,
    Strategy,
    
    # Registry
    AgentRegistry,
    AgentRegistryError,
    AgentSpec,
    global_agent_registry,
)
```

## Contributing

When adding new functionality to the agent module:

1. Follow existing patterns (context managers, error handling)
2. Add comprehensive type hints
3. Include docstrings with examples
4. Write tests covering edge cases
5. Update this README with new features

## License

SPDX-License-Identifier: MIT
