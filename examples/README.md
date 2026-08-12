---
owner: dx@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# GeoSync Examples

This directory contains practical examples demonstrating GeoSync capabilities.

## Quick Start

### Simplest Example

Start here if you're new to GeoSync:

```bash
python examples/quick_start.py
```

**What it demonstrates**:
- Basic indicator usage (Kuramoto, Entropy)
- Simple backtesting workflow
- Performance metrics analysis

## Key Use-Case Quickstarts (requirements.lock compatible)

The following scenarios are validated against `requirements.lock`. Each
dependency listed is pinned there, and the same commands are executed as CI
smoke tests.

| Use-case | Quickstart | Dependencies (version lock) |
| --- | --- | --- |
| Market regime snapshot (core indicators) | `python examples/quick_start.py --seed 7 --num-points 400` | `numpy==2.3.3`, `pandas==2.3.3` |
| Strategy backtest (GeoSync HPC) | `python examples/neuro_geosync_backtest.py` | `numpy==2.3.3`, `pandas==2.3.3` |
| Real-time style snapshot (signal generation) | `python examples/neuro_geosync_snapshot.py` | `numpy==2.3.3`, `pandas==2.3.3` |
| Integrated risk management pipeline | `python examples/integrated_risk_management_example.py` | `numpy==2.3.3` |

## Example Catalog (Seeds + Dependencies)

Every script in `examples/` is tracked in
[`docs/examples/examples_manifest.yaml`](../docs/examples/examples_manifest.yaml),
including deterministic seeds and pinned dependency versions.

## Examples by Category

### 🎯 Backtesting & Strategies

#### `neuro_geosync_backtest.py`
Advanced backtesting with the GeoSync HPC framework.

**Features**:
- Regime-sensitive decision making
- Conformal quantile regression for predictions
- SABRE Conformal Action Layer for risk control
- Walk-forward validation

**Run it**:
```bash
python examples/neuro_geosync_backtest.py --config configs/demo.yaml
```

#### `performance_demo.py`
Performance benchmarking and optimization examples.

**Features**:
- Indicator computation benchmarks
- Memory profiling
- Parallel processing demonstrations
- GPU acceleration examples

**Run it**:
```bash
python examples/performance_demo.py
```

### 📊 Market Analysis

#### `neuro_geosync_snapshot.py`
Real-time market regime analysis and snapshot generation.

**Features**:
- Current market state assessment
- Kuramoto-Ricci composite analysis
- Phase detection and confidence scoring
- Risk level evaluation

**Run it**:
```bash
python examples/neuro_geosync_snapshot.py
```

### 🧠 Advanced Features

#### `ecs_motivation_integration.py`
Emotion-Cognition System with fractal motivation engine.

**Features**:
- Allostasis-aware control
- Thompson sampling for strategy selection
- Intrinsic motivation signals
- Real-time telemetry

**Run it**:
```bash
python examples/ecs_motivation_integration.py
```

#### `ecs_regulator_demo.py`
ECS regulator demonstration with cognitive control.

**Features**:
- Energy-based regulation
- Adaptive thresholds
- Crisis detection and response

**Run it**:
```bash
python examples/ecs_regulator_demo.py
```

#### `fractal_regulator_demo.py`
Fractal regulation and multi-scale analysis.

**Features**:
- Multi-timeframe synchronization
- Fractal pattern detection
- Recursive indicator composition

**Run it**:
```bash
python examples/fractal_regulator_demo.py
```

### 🔬 HPC & AI Integration

#### `hpc_ai_v4_demo.py`
High-performance computing and AI integration demo.

**Features**:
- Distributed computing setup
- GPU-accelerated indicators
- Large-scale backtesting
- Ray or Dask integration examples

**Run it**:
```bash
python examples/hpc_ai_v4_demo.py
```

#### `thermo_hpc_ai_integration.py`
Thermodynamic control layer with HPC/AI.

**Features**:
- TACL (Thermodynamic Autonomic Control Layer)
- Free energy optimization
- Crisis-aware genetic algorithms
- Protocol hot-swapping

**Run it**:
```bash
python examples/thermo_hpc_ai_integration.py
```

## Running Examples

### Prerequisites

Ensure you have GeoSync installed:

```bash
pip install -e .
# Or with all extras:
pip install -e ".[dev,connectors,feature_store]"
```

### Basic Execution

Most examples can be run directly:

```bash
python examples/<example_name>.py
```

### With Configuration

Some examples support Hydra configuration:

```bash
python examples/<example_name>.py --config-name=prod
```

### With Arguments

Check individual example help:

```bash
python examples/<example_name>.py --help
```

## Example Output

### Typical Console Output

```
=== GeoSync Example: Quick Start ===

Loading data...
Computing indicators...
  Kuramoto Order: 0.7234
  Entropy: 2.4561
  Hurst Exponent: 0.6123

Running backtest...
  Initial Capital: $100,000
  Final Value: $115,234
  Total Return: 15.23%
  Sharpe Ratio: 1.87
  Max Drawdown: -8.45%
  Total Trades: 127
  Win Rate: 58.3%

Performance metrics saved to: results/quick_start_20240101.json
Equity curve saved to: results/equity_curve.csv
```

### Generated Files

Examples typically create:
- `results/` - Performance reports and metrics
- `logs/` - Execution logs
- `plots/` - Visualization outputs (if matplotlib available)
- `state/` - Checkpoints and intermediate states

## Modifying Examples

### Using Your Own Data

Most examples use synthetic data by default. To use real data:

```python
# Instead of synthetic data:
# prices = generate_synthetic_prices()

# Load your CSV:
import pandas as pd
data = pd.read_csv('your_data.csv')
prices = data['close'].values
```

### Adjusting Parameters

Examples use sensible defaults. Customize them:

```python
# In the example file, modify:
WINDOW_SIZE = 100  # Change from default 50
THRESHOLD = 0.8    # Change from default 0.7

# Or use command-line args if supported:
python example.py --window-size=100 --threshold=0.8
```

### Saving Results

Add custom output:

```python
import json

# Save custom metrics
results = {
    'pnl': final_pnl,
    'sharpe': sharpe_ratio,
    'custom_metric': my_metric
}

with open('my_results.json', 'w') as f:
    json.dump(results, f, indent=2)
```

## Common Patterns

### Standard Example Structure

```python
#!/usr/bin/env python
"""Brief description of what this example demonstrates."""

import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Main execution function."""
    logger.info("Starting example...")
    
    # 1. Setup
    # 2. Data loading
    # 3. Indicator computation
    # 4. Analysis/backtesting
    # 5. Results output
    
    logger.info("Example completed!")

if __name__ == "__main__":
    main()
```

### Error Handling

```python
try:
    result = run_backtest(data)
except Exception as e:
    logger.error(f"Backtest failed: {e}")
    logger.exception("Full traceback:")
    raise
```

### Progress Tracking

```python
from tqdm import tqdm

for i in tqdm(range(len(data)), desc="Processing"):
    # Process each data point
    pass
```

## Example Data

Some examples include sample data in `examples/data/`:

- `sample_prices.csv` - Synthetic price data
- `sample_ticks.csv` - High-frequency tick data
- `sample_ohlcv.csv` - OHLCV bar data

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'geosync'`

**Solution**:
```bash
# Install from project root
cd /path/to/GeoSync
pip install -e .
```

### Missing Data

**Problem**: Example can't find data file

**Solution**:
```bash
# Run from project root, not examples directory
cd /path/to/GeoSync
python examples/quick_start.py

# OR update paths in the example
```

### Memory Issues

**Problem**: Out of memory errors

**Solution**:
- Use smaller datasets initially
- Enable chunked processing
- Reduce indicator window sizes
- Use GPU acceleration if available

See [Troubleshooting Guide](../docs/troubleshooting.md) for more help.

## Creating Your Own Example

### Template

Use this template for new examples:

```python
#!/usr/bin/env python
"""
<Title>: <One-line description>

This example demonstrates:
- Feature 1
- Feature 2
- Feature 3
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from core.indicators import <your_indicators>
from backtest import <your_backtest_components>

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_sample_data() -> pd.DataFrame:
    """Generate or load sample data."""
    # Your data generation/loading code
    pass


def run_analysis(data: pd.DataFrame) -> dict:
    """Run your analysis."""
    # Your analysis code
    pass


def save_results(results: dict, output_path: Path) -> None:
    """Save results to file."""
    # Your output code
    pass


def main():
    """Main execution."""
    logger.info("Starting example: <your title>")
    
    try:
        # 1. Generate/load data
        data = generate_sample_data()
        logger.info(f"Loaded {len(data)} data points")
        
        # 2. Run analysis
        results = run_analysis(data)
        logger.info(f"Analysis complete. PnL: ${results['pnl']:,.2f}")
        
        # 3. Save results
        output_path = Path("results") / "my_example_results.json"
        output_path.parent.mkdir(exist_ok=True)
        save_results(results, output_path)
        logger.info(f"Results saved to {output_path}")
        
    except Exception as e:
        logger.error(f"Example failed: {e}")
        raise


if __name__ == "__main__":
    main()
```

### Best Practices

1. **Self-contained**: Example should run without external dependencies
2. **Well-documented**: Include docstrings and comments
3. **Reproducible**: Use fixed random seeds
4. **Logging**: Use logging instead of print statements
5. **Error handling**: Catch and log exceptions appropriately
6. **Clean output**: Save results to files, don't clutter console

## Contributing Examples

Want to add an example? See [Contributing Guide](../CONTRIBUTING.md).

Good examples to contribute:
- Real-world strategy implementations
- Integration with external data sources
- Novel indicator combinations
- Performance optimization techniques
- Error handling patterns

## Additional Resources

- [API Examples](../docs/api_examples.md) - Code snippets for common tasks
- [Quick Start Guide](../docs/quickstart.md) - Getting started tutorial
- [Indicators Guide](../docs/indicators.md) - Detailed indicator documentation
- [Backtesting Guide](../docs/backtest.md) - Backtesting framework details

## Questions?

- [Discord Community](https://discord.gg/geosync)
- [GitHub Discussions](https://github.com/neuron7xLab/GeoSync/discussions)
- [Documentation](https://docs.geosync.io)

---

**Note**: Examples are for educational purposes. Always test strategies thoroughly in paper trading before risking real capital.
