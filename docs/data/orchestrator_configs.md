---
owner: neuro@tradepulse
review_cadence: monthly
artifacts:
  - path: artifacts/orchestrator_config_v1.json
    checksum: sha256:df9386bb9a3f9a3cc7640ce0bf12837c028034848af27970ac20d4381c8d7ae6
    size_bytes: 1403
---

# Orchestrator Configuration Artifacts

## Overview

This dataset contract defines validated configuration artifacts for the TradePulse Neuro-Orchestrator system. These configurations define module execution sequences, parameter settings, and neuromodulator configurations for various trading scenarios.

## Artifacts

### artifacts/orchestrator_config_v1.json

**Format**: JSON (JavaScript Object Notation)

**Description**: Standard production-ready orchestrator configuration for dopamine-enhanced backtesting. This configuration represents a complete, validated setup that coordinates data ingestion, feature extraction, risk assessment, and action selection with neuromodulator integration.

**Schema**:

```json
{
  "metadata": {
    "name": string,            // Configuration name identifier
    "version": string,         // Semantic version (e.g., "1.0.0")
    "created": string,         // ISO 8601 timestamp
    "description": string      // Human-readable description
  },
  "module_sequence": [
    {
      "module_name": string,   // Module identifier
      "operation": string,     // Operation to perform
      "parameters": {          // Module-specific parameters
        ...
      },
      "priority": integer      // Execution order (0 = first)
    }
  ],
  "parameters": {
    "capital": float,                    // Initial trading capital
    "max_position_size": float,          // Max position as fraction of capital (0-1)
    "learning_rate": float,              // Learning rate for TD(0) updates
    "discount_gamma": float,             // Discount factor for future rewards
    "exposure_limit": float              // Maximum portfolio exposure (0-1)
  }
}
```

**Characteristics**:
- **Complete Pipeline**: All essential modules from data ingestion to action selection
- **Validated Parameters**: All parameters within safe operational ranges
- **Neuromodulator Integration**: Configured for dopamine, serotonin, GABA, and NA/ACh systems
- **Production Ready**: Can be used directly in live trading (with appropriate risk controls)
- **Versioned**: Includes metadata for configuration version tracking

**Module Sequence Details**:

1. **data_ingestion** (Priority 0)
   - Ingests market data for specified symbol and timeframe
   - Buffer size: 1000 periods
   - Symbol: BTC/USDT (configurable)
   - Timeframe: 1 hour (configurable)

2. **feature_extraction** (Priority 1)
   - Calculates geometric and thermodynamic indicators
   - Indicators: Kuramoto synchronization, Ricci flow, entropy
   - Lookback window: 100 periods

3. **risk_assessment** (Priority 2)
   - Evaluates portfolio risk using VaR-ES methodology
   - Confidence level: 95%
   - Rolling window: 50 periods

4. **action_selector** (Priority 3)
   - Selects trading actions using basal ganglia model
   - Temperature: 1.0 (balanced exploration/exploitation)
   - Neuromodulators: All four systems active

**Parameter Rationale**:

- **Capital (100,000)**: Standard test capital allowing realistic position sizing
- **Max Position Size (0.2)**: Conservative 20% limit per position
- **Learning Rate (0.01)**: Standard TD(0) learning rate
- **Discount Gamma (0.99)**: Values near-term and future rewards appropriately
- **Exposure Limit (0.5)**: Maximum 50% portfolio exposure at any time

**Use Cases**:
- **Backtesting**: Standard configuration for historical testing
- **Paper Trading**: Safe configuration for simulated live trading
- **Production Template**: Starting point for live trading configurations
- **Documentation**: Reference example for configuration structure
- **Integration Testing**: Validates orchestrator pipeline end-to-end
- **Performance Benchmarking**: Consistent configuration for performance comparisons

**Safety Features**:
- Conservative position sizing limits
- Comprehensive risk assessment module
- Neuromodulator-based impulse control
- Exposure limits to prevent over-leveraging
- Multi-stage validation before execution

## Configuration Validation

To validate orchestrator configurations programmatically:

```python
import json
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError

class OrchestratorConfig(BaseModel):
    """Pydantic model for orchestrator configuration validation."""
    
    class Metadata(BaseModel):
        name: str
        version: str
        created: str
        description: str
    
    class ModuleSpec(BaseModel):
        module_name: str
        operation: str
        parameters: dict
        priority: int = Field(ge=0)
    
    class Parameters(BaseModel):
        capital: float = Field(gt=0)
        max_position_size: float = Field(ge=0, le=1)
        learning_rate: float = Field(gt=0, le=1)
        discount_gamma: float = Field(ge=0, le=1)
        exposure_limit: float = Field(ge=0, le=1)
    
    metadata: Metadata
    module_sequence: list[ModuleSpec]
    parameters: Parameters

# Load and validate
config_path = Path("artifacts/orchestrator_config_v1.json")
with config_path.open() as f:
    config_data = json.load(f)

try:
    config = OrchestratorConfig(**config_data)
    print(f"✓ Configuration '{config.metadata.name}' is valid")
except ValidationError as e:
    print(f"✗ Configuration validation failed: {e}")
```

## Integration Examples

### Loading Configuration

```python
import json
from pathlib import Path

def load_orchestrator_config(config_name: str = "v1") -> dict:
    """Load validated orchestrator configuration."""
    config_path = Path(f"artifacts/orchestrator_config_{config_name}.json")
    with config_path.open() as f:
        return json.load(f)

config = load_orchestrator_config("v1")
print(f"Loaded: {config['metadata']['name']}")
print(f"Modules: {len(config['module_sequence'])}")
```

### Using in Backtests

```python
from backtest.orchestrator import NeuroOrchestrator

# Load configuration
config = load_orchestrator_config("v1")

# Initialize orchestrator
orchestrator = NeuroOrchestrator(config)

# Run backtest
results = orchestrator.run_backtest(
    start_date="2024-01-01",
    end_date="2024-12-31"
)

print(f"Final P&L: ${results.total_pnl:,.2f}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
```

### Customizing Configuration

```python
import copy

# Load base configuration
base_config = load_orchestrator_config("v1")

# Create variant with higher learning rate
aggressive_config = copy.deepcopy(base_config)
aggressive_config['metadata']['name'] = 'aggressive_learning'
aggressive_config['parameters']['learning_rate'] = 0.05
aggressive_config['parameters']['max_position_size'] = 0.3

# Save variant
with open('artifacts/orchestrator_config_aggressive.json', 'w') as f:
    json.dump(aggressive_config, f, indent=2)
```

## Version History

### v1.0.0 (2025-11-17)
- **Initial Release**: Standard dopamine-enhanced configuration
- **Modules**: 4-stage pipeline (ingest → extract → assess → select)
- **Capital**: $100,000 default
- **Risk Controls**: Conservative position sizing and exposure limits
- **Neuromodulators**: Full integration (DA, 5-HT, GABA, NA/ACh)

## Best Practices

### Configuration Management

1. **Versioning**: Always include semantic version in metadata
2. **Immutability**: Treat configurations as immutable; create new versions for changes
3. **Validation**: Validate configurations before use
4. **Documentation**: Include clear descriptions in metadata
5. **Testing**: Test new configurations in sandbox before production

### Parameter Selection

1. **Capital**: Use realistic amounts for your use case
2. **Position Sizing**: Start conservative (≤0.2), adjust with proven track record
3. **Learning Rate**: Standard range 0.001-0.1; lower for stability
4. **Discount Gamma**: 0.95-0.99 typical; higher values favor long-term planning
5. **Exposure**: Never exceed 0.8 unless exceptional risk tolerance

### Module Configuration

1. **Priority**: Ensure logical execution order (data → features → risk → action)
2. **Parameters**: Keep module parameters within validated ranges
3. **Indicators**: Select indicators appropriate for market regime
4. **Risk Methods**: Use VaR-ES for comprehensive downside protection
5. **Neuromodulators**: Enable all four for balanced decision-making

## Related Documentation

- [Orchestrator Implementation](../../examples/orchestrator_output_example.json)
- [Neuro-Orchestrator Guide](../../NEURO_ORCHESTRATOR_IMPLEMENTATION.md)
- [Dopamine Loop Documentation](../../DOPAMINE_LOOP_IMPLEMENTATION.md)
- [Risk Assessment](../../core/risk/)

## Troubleshooting

### Invalid Module Name

**Error**: `Unknown module: xyz`

**Solution**: Check module name against registered modules in orchestrator registry.

### Parameter Out of Range

**Error**: `max_position_size must be between 0 and 1`

**Solution**: Ensure all fraction parameters (position size, exposure limit) are in [0, 1].

### Priority Conflicts

**Error**: `Duplicate priority: 2`

**Solution**: Each module must have unique priority. Adjust priorities to create clear execution order.

## Maintenance

**Update Frequency**: Monthly review of configuration parameters based on:
- Market regime changes
- Performance analysis results
- Risk metric trends
- Neuromodulator tuning insights

**Update Process**:
1. Create new configuration file with incremented version
2. Update checksum in this contract
3. Document changes in version history
4. Validate with test suite
5. Deploy to staging environment
6. Monitor performance
7. Promote to production if validated

## Changelog

### 2025-11-17
- Initial contract creation
- Documented orchestrator_config_v1.json artifact
- Added schema definition and validation examples
- Included integration examples and best practices
- Defined maintenance procedures
