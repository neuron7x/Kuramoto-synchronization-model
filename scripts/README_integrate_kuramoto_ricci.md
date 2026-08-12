# integrate_kuramoto_ricci.py

Run the Kuramoto-Ricci composite integration pipeline for advanced market analysis.

## Description

This CLI utility executes the Kuramoto-Ricci composite integration pipeline, which combines:
- **Kuramoto oscillator synchronization**: Measures market coupling and phase transitions
- **Ricci curvature analysis**: Identifies geometric market structures and stability
- **Multi-scale integration**: Analyzes market dynamics across different timeframes

The script processes market data and generates composite indicators for trading strategy development.

## Usage

### Basic run with defaults

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data data/sample.csv
```

### Specify custom configuration

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data data/market_data.csv \
  --config configs/kuramoto_ricci.yaml
```

### Custom output directory

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data data/sample.csv \
  --output reports/kuramoto-ricci-$(date +%Y%m%d)
```

### Override configuration values

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data data/sample.csv \
  --config-override kuramoto.coupling_strength=0.5 \
  --config-override ricci.threshold=-0.1
```

### Dry run (show plan without execution)

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data data/sample.csv \
  --dry-run
```

### Non-interactive mode (skip confirmations)

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data data/sample.csv \
  --yes
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--data` | (required) | Path to input data (CSV or directory) |
| `--config` | `$KURAMOTO_RICCI_CONFIG` or default | Configuration YAML file |
| `--output` | `$KURAMOTO_RICCI_OUTPUT_DIR` or default | Output directory for results |
| `--config-override` | `[]` | Override config values (format: `key.subkey=value`) |
| `--dry-run` | `False` | Show execution plan without running |
| `--yes` | `False` | Skip confirmation prompts |

## Configuration

The script reads configuration from a YAML file with the following structure:

```yaml
kuramoto:
  coupling_strength: 0.3
  natural_frequency_std: 0.1
  timeframes:
    - "5m"
    - "15m"
    - "1h"

ricci:
  threshold: -0.05
  curvature_window: 20
  
composite:
  weight_kuramoto: 0.6
  weight_ricci: 0.4
```

Configuration can be overridden via CLI:

```bash
--config-override kuramoto.coupling_strength=0.5
--config-override composite.weight_kuramoto=0.7
```

## Output

The script generates several output files:

- `composite_indicators.csv`: Combined Kuramoto-Ricci signals
- `kuramoto_analysis.json`: Synchronization metrics
- `ricci_curvature.csv`: Geometric curvature values
- `config_used.yaml`: Configuration snapshot
- `metadata.json`: Run metadata and statistics

## Exit Codes

- `0`: Success
- `1`: Invalid configuration
- `2`: Data not found
- `3`: Output directory error
- `4`: Processing error

## Examples

### Production run with monitoring

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data /data/live/btc_usd.csv \
  --config configs/production.yaml \
  --output /results/$(date +%Y-%m-%d) \
  --yes
```

### Research experiment with overrides

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data research/experiment_data.csv \
  --config configs/baseline.yaml \
  --config-override kuramoto.coupling_strength=0.8 \
  --config-override ricci.threshold=-0.2 \
  --output research/results/exp001
```

### Dry run for validation

```bash
python scripts/integrate_kuramoto_ricci.py \
  --data data/test.csv \
  --config configs/new_params.yaml \
  --dry-run
```

### Multi-asset batch processing

```bash
for asset in BTC ETH SOL; do
  python scripts/integrate_kuramoto_ricci.py \
    --data data/${asset}_USD.csv \
    --output reports/kuramoto-ricci/${asset} \
    --yes
done
```

## Environment Variables

- `KURAMOTO_RICCI_CONFIG`: Default configuration file path
- `KURAMOTO_RICCI_OUTPUT_DIR`: Default output directory

Example:

```bash
export KURAMOTO_RICCI_CONFIG=/configs/production.yaml
export KURAMOTO_RICCI_OUTPUT_DIR=/results/kuramoto-ricci

python scripts/integrate_kuramoto_ricci.py --data data/sample.csv
```

## Requirements

- Python 3.11+
- pandas
- numpy
- scipy
- networkx
- pyyaml
- GeoSync core modules (core.indicators, core.config)

## Performance

Processing time depends on:
- Data size (rows)
- Number of timeframes
- Kuramoto coupling iterations
- Ricci curvature window size

Typical performance:
- 10K rows: ~5-10 seconds
- 100K rows: ~1-2 minutes
- 1M rows: ~10-20 minutes

## Use Cases

1. **Market regime detection**: Identify phase transitions and regime changes
2. **Correlation analysis**: Measure multi-asset synchronization
3. **Stability assessment**: Detect geometric instabilities via Ricci curvature
4. **Trading strategy development**: Generate composite signals
5. **Research**: Experiment with geometric market analysis
