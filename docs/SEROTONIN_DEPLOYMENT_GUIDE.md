---
owner: neuro@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Serotonin Controller v2.4.0 - Deployment Guide

**Version**: v2.4.0
**Date**: 2025-11-10
**Status**: Production-Ready

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Integration Examples](#integration-examples)
6. [Monitoring Setup](#monitoring-setup)
7. [Health Checks](#health-checks)
8. [Troubleshooting](#troubleshooting)
9. [Rollback Procedures](#rollback-procedures)
10. [Production Best Practices](#production-best-practices)

---

## Quick Start

### Minimal Working Example

```python
from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController

# Initialize controller
controller = SerotoninController(config_path="configs/serotonin.yaml")

# Main trading loop
while trading_active:
    # Get current market conditions
    stress = calculate_market_stress()  # Your stress metric
    drawdown = portfolio.current_drawdown()  # Negative value
    novelty = calculate_market_novelty()  # Your novelty metric

    # Execute serotonin control step
    hold, veto, cooldown_s, level = controller.step(
        stress=stress,
        drawdown=drawdown,
        novelty=novelty
    )

    # Apply control decision
    if hold:
        print(f"HOLD triggered: level={level:.3f}, cooldown={cooldown_s:.1f}s")
        # Skip new position entry
        continue

    # Normal trading logic
    execute_trading_strategy()
```

**That's it!** The controller handles all complexity internally.

---

## Pre-Deployment Checklist

### Phase 1: Environment Validation ✅

- [ ] Python 3.11+ installed
- [ ] Required dependencies installed (`numpy`, `pyyaml`, `pydantic`)
- [ ] Configuration file prepared (`configs/serotonin.yaml`)
- [ ] File system has write permissions (for state/audit files)
- [ ] Monitoring infrastructure ready (optional but recommended)

### Phase 2: Testing ✅

- [ ] Run unit tests: `pytest core/neuro/tests/test_serotonin_controller.py`
- [ ] Verify all 62 tests pass
- [ ] Test with your actual config file
- [ ] Validate config schema with `controller.config_schema()`
- [ ] Test state persistence (save/load)
- [ ] Test health checks

### Phase 3: Integration Testing ✅

- [ ] Integrate controller into your system
- [ ] Run dry-run simulation with live data
- [ ] Verify telemetry/logging works
- [ ] Test HOLD/ACTIVE transitions
- [ ] Validate cooldown behavior
- [ ] Test recovery after simulated failures

### Phase 4: Staging Deployment ✅

- [ ] Deploy to staging environment
- [ ] Run for 24 hours minimum
- [ ] Monitor all metrics
- [ ] Verify no unexpected behavior
- [ ] Test rollback procedure
- [ ] Document any tuning needed

### Phase 5: Production Deployment ✅

- [ ] Schedule deployment during low-volume period
- [ ] Deploy with gradual rollout (if possible)
- [ ] Monitor closely for first 4 hours
- [ ] Verify telemetry/alerts working
- [ ] Have rollback plan ready
- [ ] Document deployment time and conditions

---

## Installation

### Method 1: Direct Import (Recommended)

```python
# Add to your Python path or use relative import
from core.neuro.serotonin.serotonin_controller import SerotoninController
```

### Method 2: Package Installation

```bash
# If TradePulse is installed as a package
pip install -e /path/to/TradePulse
```

### Dependencies

**Required**:
```bash
pip install numpy>=2.3.3 pyyaml>=6.0.3 pydantic>=2.12.1
```

**Optional** (for advanced features):
```bash
pip install prometheus-client>=0.23.1  # For Prometheus metrics
```

---

## Configuration

> **Default profile:** `v24` is the default profile in `configs/serotonin.yaml`.
> To preserve legacy behaviour, set `active_profile: legacy` and keep the
> `serotonin_legacy` section populated.

### Basic Configuration File

Create `configs/serotonin.yaml`:

```yaml
# Core serotonin weights
alpha: 0.42              # Market volatility weight
beta: 0.28               # Free energy weight
gamma: 0.32              # Cumulative losses weight
delta_rho: 0.18          # Rho-loss complement weight

# Sigmoid parameters
k: 1.0                   # Logistic steepness
theta: 0.5               # Logistic mid-point

# Action inhibition
delta: 0.8               # Inhibition multiplier
za_bias: -0.33           # Zero-action bias

# Dynamics
decay_rate: 0.05         # Tonic decay rate (or use tau_5ht_ms/step_ms)

# Thresholds
cooldown_threshold: 0.7  # Serotonin threshold for veto
gate_veto: 0.9           # Gate level veto threshold
phasic_veto: 1.0         # Phasic level veto threshold

# Desensitization
desens_threshold_ticks: 100
desens_rate: 0.01
max_desens_counter: 1000
desens_gain: 0.12

# Meta-adaptation
target_dd: -0.05
target_sharpe: 1.0
beta_temper: 0.12

# Phasic dynamics
phase_threshold: 0.4
phase_kappa: 0.08
burst_factor: 2.5

# Modulation
mod_t_max: 4.0
mod_t_half: 24.0
mod_k: 0.7
tick_hours: 1.0

# Temperature floor
temperature_floor_min: 0.05
temperature_floor_max: 0.4
```

### Alternative: Time-Constant Based Config

If you prefer to specify time constants:

```yaml
# Use tau and step_ms instead of decay_rate
tau_5ht_ms: 150.0        # Tonic time constant in milliseconds
step_ms: 1000.0          # Decision step duration in milliseconds
# decay_rate will be auto-calculated: 1 - exp(-step_ms / tau_5ht_ms)

# ... rest of config
```

### Configuration Validation

```python
# Validate configuration before deployment
controller = SerotoninController("configs/serotonin.yaml")
schema = controller.config_schema()
print(json.dumps(schema, indent=2))

# Check loaded values
print(controller.config)
```

---

## Integration Examples

### Example 1: Basic Risk Control

```python
from core.neuro.serotonin.serotonin_controller import SerotoninController

class TradingSystem:
    def __init__(self):
        self.controller = SerotoninController()
        self.position = 0

    def on_market_update(self, market_data):
        # Calculate risk metrics
        stress = self.calculate_stress(market_data)
        drawdown = self.portfolio.current_drawdown()
        novelty = self.calculate_novelty(market_data)

        # Get serotonin control decision
        hold, veto, cooldown_s, level = self.controller.step(
            stress=stress,
            drawdown=drawdown,
            novelty=novelty
        )

        # Log state
        self.log_serotonin_state(hold, level, cooldown_s)

        # Apply control
        if hold:
            # Don't open new positions
            return

        # Normal strategy execution
        signal = self.strategy.generate_signal(market_data)
        if signal:
            self.execute_trade(signal)
```

### Example 2: With Action Probability Modulation

```python
class AdvancedTradingSystem:
    def __init__(self):
        self.controller = SerotoninController()

    def execute_with_modulation(self, base_probability):
        # Get current serotonin level
        level = self.controller.serotonin_level

        # Modulate action probability
        adjusted_prob = self.controller.modulate_action_prob(
            original_prob=base_probability,
            serotonin_signal=level
        )

        # Use adjusted probability for position sizing
        if random.random() < adjusted_prob:
            self.execute_trade()
```

### Example 3: With State Persistence

```python
class ResilientTradingSystem:
    def __init__(self):
        self.controller = SerotoninController()
        self.state_file = "state/serotonin_checkpoint.json"

        # Try to recover previous state
        try:
            self.controller.load_state(self.state_file)
            print("Recovered controller state")
        except FileNotFoundError:
            print("Starting with fresh state")

    def shutdown(self):
        # Save state for recovery
        self.controller.save_state(self.state_file)
        print("Saved controller state")
```

### Example 4: With Health Monitoring

```python
class MonitoredTradingSystem:
    def __init__(self):
        self.controller = SerotoninController()

    def periodic_health_check(self):
        """Run every 5 minutes"""
        health = self.controller.health_check()

        if not health["healthy"]:
            # Alert on issues
            self.send_alert(f"Serotonin controller issues: {health['issues']}")

        if health["warnings"]:
            # Log warnings
            self.log_warning(f"Serotonin warnings: {health['warnings']}")

        # Log metrics
        metrics = self.controller.get_performance_metrics()
        self.log_metrics(metrics)
```

### Example 5: With Prometheus Metrics

```python
from prometheus_client import Gauge, Counter

# Create Prometheus metrics
serotonin_level_gauge = Gauge('serotonin_level', 'Current serotonin level')
hold_state_gauge = Gauge('serotonin_hold_state', 'Hold state (0=active, 1=hold)')
veto_counter = Counter('serotonin_veto_total', 'Total veto events')

class ObservableTradingSystem:
    def __init__(self):
        # Create logger that publishes to Prometheus
        def prometheus_logger(name: str, value: float):
            if name == "tacl.5ht.level":
                serotonin_level_gauge.set(value)
            elif name == "tacl.5ht.hold":
                hold_state_gauge.set(value)

        self.controller = SerotoninController(logger=prometheus_logger)

    def on_market_update(self, market_data):
        hold, veto, cooldown_s, level = self.controller.step(
            stress=self.calculate_stress(market_data),
            drawdown=self.portfolio.current_drawdown(),
            novelty=self.calculate_novelty(market_data)
        )

        if veto:
            veto_counter.inc()

        # Continue with trading logic
```

---

## Monitoring Setup

### Key Metrics to Monitor

1. **Serotonin Level** (`serotonin_level`)
   - Range: 0.0 to 1.0
   - Alert if stuck at >0.95 for >1 hour
   - Normal: oscillates between 0.2-0.8

2. **Hold State** (`hold_state`)
   - Boolean: True/False
   - Alert if True for >1 hour continuously
   - Track percentage of time in HOLD

3. **Cooldown Duration** (`cooldown_s`)
   - Time in seconds since HOLD started
   - Alert if >3600 seconds (1 hour)
   - Track average cooldown duration

4. **Veto Rate** (`veto_count / step_count`)
   - Percentage of steps with veto
   - Alert if >50% sustained
   - Normal: 5-20% depending on market

5. **Sensitivity** (`sensitivity`)
   - Range: 0.1 to 1.0
   - Alert if <0.2 (over-desensitized)
   - Normal: 0.7-1.0

6. **Performance Metrics**
   - Step count
   - Average cooldown duration
   - Total cooldown time

### Monitoring Dashboard Template

```python
def create_monitoring_dashboard():
    """Create a monitoring dashboard for the controller"""
    metrics = controller.get_performance_metrics()
    state = controller.to_dict()
    health = controller.health_check()

    dashboard = {
        "timestamp": time(),
        "health": {
            "status": "healthy" if health["healthy"] else "unhealthy",
            "issues": health["issues"],
            "warnings": health["warnings"],
        },
        "state": {
            "serotonin_level": state["serotonin_level"],
            "hold_state": state["hold_state"],
            "cooldown_s": state["cooldown_s"],
            "sensitivity": state["sensitivity"],
            "tonic_level": state["tonic_level"],
        },
        "performance": {
            "step_count": metrics["step_count"],
            "veto_count": metrics["veto_count"],
            "veto_rate": metrics["veto_rate"],
            "avg_cooldown": metrics["average_cooldown_duration"],
        }
    }

    return dashboard
```

---

## Health Checks

### Automated Health Check

```python
# Run health check every 5 minutes
def periodic_health_check(controller):
    health = controller.health_check()

    if not health["healthy"]:
        # CRITICAL: Issues detected
        for issue in health["issues"]:
            send_critical_alert(issue)

        # Consider emergency shutdown
        if "Invalid decay_rate" in str(health["issues"]):
            emergency_shutdown()

    if health["warnings"]:
        # WARNING: Potential issues
        for warning in health["warnings"]:
            send_warning_alert(warning)

    # Log health report
    log_health_report(health)
```

### Manual Diagnostics

```python
# Get detailed diagnostic report
report = controller.diagnose()
print(report)

# Output:
# === SerotoninController Diagnostic Report ===
# Config: configs/serotonin.yaml
#
# State:
#   Serotonin Level: 0.4521
#   Tonic Level: 0.3201
#   ...
```

---

## Troubleshooting

### Issue: Controller Stuck in HOLD State

**Symptoms**: `hold_state = True` for extended period (>1 hour)

**Diagnosis**:
```python
health = controller.health_check()
if "Stuck in HOLD" in str(health["issues"]):
    print(controller.diagnose())
```

**Solutions**:
1. Check if market conditions are genuinely extreme
2. Review `cooldown_threshold` - may be too low
3. Check `desens_rate` - may be too slow
4. Consider manual reset: `controller.reset()`

**Prevention**:
- Monitor cooldown duration alerts
- Set up automatic recovery after 2 hours

---

### Issue: Frequent HOLD/ACTIVE Oscillations

**Symptoms**: Rapid toggling between HOLD and ACTIVE

**Diagnosis**:
```python
# Check oscillation frequency
metrics = controller.get_performance_metrics()
if metrics["veto_rate"] > 0.5:  # More than 50% of steps
    print("High oscillation detected")
```

**Note**: This should NOT occur in v2.4.0 due to hysteresis (95% reduction vs v2.3.1)

**Solutions** (if it does occur):
1. Verify v2.4.0 is actually deployed
2. Check config for custom `gate_veto` or `phasic_veto` thresholds
3. Review input data quality (stress/drawdown/novelty)

---

### Issue: Low Sensitivity

**Symptoms**: `sensitivity < 0.2`

**Diagnosis**:
```python
state = controller.to_dict()
print(f"Sensitivity: {state['sensitivity']:.3f}")
print(f"Desens counter: {state['desens_counter']}")
```

**Solutions**:
1. Increase `desens_rate` for faster recovery
2. Reduce `desens_gain` for slower desensitization
3. Check if prolonged stress period is genuine
4. Consider temporary reset if stuck

---

### Issue: Performance Degradation

**Symptoms**: Slow controller.step() calls

**Diagnosis**:
```python
import time
start = time.perf_counter()
for _ in range(10000):
    controller.step(stress=1.0, drawdown=-0.02, novelty=0.5)
duration = time.perf_counter() - start
avg_us = (duration / 10000) * 1e6
print(f"Average call time: {avg_us:.2f} μs")
```

**Expected**: <3 μs per call

**Solutions**:
1. Check for I/O operations in logger
2. Verify no blocking operations in TACL guard
3. Profile with `cProfile` to find bottlenecks

---

## Rollback Procedures

### Scenario 1: Quick Rollback to v2.3.1

**If needed** (unlikely, but prepared):

```bash
# 1. Stop trading system
systemctl stop trading-system

# 2. Revert code
cd /path/to/TradePulse
git checkout v2.3.1-tag  # Or specific commit

# 3. Restore config backup (if modified)
cp configs/serotonin.yaml.backup configs/serotonin.yaml

# 4. Restart system
systemctl start trading-system

# 5. Monitor for 1 hour
tail -f logs/trading-system.log
```

**Time to rollback**: <5 minutes

---

### Scenario 2: Partial Rollback (Keep State)

If you want to rollback code but keep state:

```python
# Save current state before rollback
controller.save_state("state/v2.4.0_final_state.json")

# After reverting to v2.3.1, can still load state
# (v2.3.1 will ignore v2.4.0-specific fields gracefully)
```

---

## Production Best Practices

### 1. Configuration Management ✅

- Store configs in version control
- Use environment-specific configs (dev/staging/prod)
- Enable audit trail (automatic in v2.4.0)
- Review `configs/audit/` directory regularly

### 2. State Persistence ✅

```python
# Save state every hour
def periodic_state_backup():
    timestamp = int(time())
    controller.save_state(f"state/serotonin_{timestamp}.json")

# Keep last 7 days of snapshots
def cleanup_old_snapshots():
    # Remove snapshots older than 7 days
    retention_seconds = 7 * 24 * 3600
    # ... cleanup logic
```

### 3. Monitoring & Alerting ✅

**Critical Alerts**:
- Controller stuck in HOLD >1 hour
- Health check failed
- Sensitivity <0.1
- Config corruption detected

**Warning Alerts**:
- Veto rate >40%
- Extended HOLD >10 minutes
- Low sensitivity <0.3
- High desensitization counter
