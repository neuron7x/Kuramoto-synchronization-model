# Core Automation Framework

## Overview

This directory contains the autonomous automation framework for TradePulse - a comprehensive system that manages 7 critical components without human intervention.

## Components

### 1. `config_automation.py`
Configuration management with auto-validation, self-healing, and drift detection.

**Key Classes**: `ConfigAutomation`, `ValidationReport`, `ConfigIssue`

### 2. `data_pipeline_automation.py`
Data pipeline quality assurance with automatic validation, cleaning, and DLQ processing.

**Key Classes**: `DataPipelineAutomation`, `DataQualityMetrics`, `DataRecord`

### 3. `strategy_automation.py`
Strategy scheduling and execution with auto-failover and rebalancing.

**Key Classes**: `StrategyAutomation`, `StrategyMetrics`, `RebalanceEvent`

### 4. `monitoring_automation.py`
Monitoring and observability with auto-triage, health checks, and incident response.

**Key Classes**: `MonitoringAutomation`, `Alert`, `Incident`, `HealthCheck`

### 5. `security_automation.py`
Security and compliance with automated secret rotation, scanning, and remediation.

**Key Classes**: `SecurityAutomation`, `Secret`, `Vulnerability`, `ComplianceCheck`

### 6. `infrastructure_automation.py`
Infrastructure management with auto-scaling, self-healing, and rollback.

**Key Classes**: `InfrastructureAutomation`, `Service`, `ScalingEvent`, `DeploymentEvent`

### 7. `testing_automation.py`
Testing and QA with auto-generation, regression detection, and prioritization.

**Key Classes**: `TestingAutomation`, `TestResult`, `TestSuite`, `PerformanceBaseline`

### 8. `orchestrator.py`
Central coordinator that manages all components and ensures system-wide health.

**Key Classes**: `AutomationOrchestrator`, `SystemHealth`, `OrchestrationCycle`

## Quick Start

### Basic Usage

```python
from core.automation import AutomationOrchestrator

# Initialize and start
orchestrator = AutomationOrchestrator(
    orchestration_interval_seconds=60,
    enable_auto_recovery=True,
)

await orchestrator.start()

# System now runs autonomously
```

### Using Individual Components

```python
from core.automation import (
    ConfigAutomation,
    DataPipelineAutomation,
    SecurityAutomation,
)

# Configuration management
config = ConfigAutomation(auto_fix=True)
report = config.validate_all_configs()

# Data pipeline
pipeline = DataPipelineAutomation(auto_clean=True)
result = await pipeline.process_data(data, "source")

# Security
security = SecurityAutomation(auto_remediate=True)
await security.rotate_secret("key-id", "Key Name")
```

## Architecture

```
AutomationOrchestrator
├── ConfigAutomation
├── DataPipelineAutomation
├── StrategyAutomation
├── MonitoringAutomation
├── SecurityAutomation
├── InfrastructureAutomation
└── TestingAutomation
```

## Key Features

✅ **Fully Autonomous**: All operations run without human intervention
✅ **Self-Healing**: Automatic detection and correction of issues
✅ **Intelligent Defaults**: Smart fallbacks for missing values
✅ **Quality Metrics**: Comprehensive monitoring across all components
✅ **Auto-Recovery**: System automatically recovers from degraded states
✅ **Zero-Downtime**: Operations complete without service interruption

## Health Status

Each component provides health status:

- `healthy`: Operating normally
- `degraded`: Operating with some issues
- `critical`: Significant issues requiring attention
- `unknown`: Status cannot be determined

## Orchestration Cycle

Each cycle:
1. Validates configurations
2. Processes data pipeline
3. Executes strategies
4. Runs health checks
5. Performs security scans
6. Scales infrastructure
7. Runs tests
8. Assesses overall health
9. Applies recovery if needed

## Demo

See `examples/automation_demo.py` for a complete working example.

## Documentation

Full documentation: `docs/AUTONOMOUS_AUTOMATION_GUIDE.md`

## Integration

Add to your application:

```python
import asyncio
from core.automation import AutomationOrchestrator

async def main():
    orchestrator = AutomationOrchestrator()
    
    # Configure components as needed
    orchestrator.config_automation.config_dirs = [Path("configs")]
    
    # Start autonomous operations
    await orchestrator.start()
    
    # Your application logic here
    # ...
    
    # Stop when done
    await orchestrator.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Development

### Adding New Automation

1. Create new automation class
2. Implement `get_health_status()` method
3. Add to orchestrator initialization
4. Add orchestration logic in `orchestrator.py`

### Testing

Each component includes placeholder test implementations. Extend these for production use.

## Best Practices

1. **Always use orchestrator** for production
2. **Monitor health status** regularly
3. **Review orchestration logs** for insights
4. **Set appropriate thresholds** for your environment
5. **Test configuration changes** before deployment

## Support

For questions or issues, see the main documentation or contact the TradePulse team.

---

**Version**: 2.0.0
**License**: LicenseRef-TradePulse-Proprietary
