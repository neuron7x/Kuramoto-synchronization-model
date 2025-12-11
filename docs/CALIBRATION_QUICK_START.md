# Calibration Quick Start Guide

## Quick Commands

### List Available Profiles
```bash
python scripts/calibrate_controllers.py --list-profiles
```

### Apply Calibration Profiles

**Conservative** (Low Risk, Tight Thresholds):
```bash
# NAK Controller
python scripts/calibrate_controllers.py --controller nak --profile conservative

# Dopamine Controller
python scripts/calibrate_controllers.py --controller dopamine --profile conservative
```

**Balanced** (Default, Moderate Risk):
```bash
# NAK Controller
python scripts/calibrate_controllers.py --controller nak --profile balanced

# Dopamine Controller
python scripts/calibrate_controllers.py --controller dopamine --profile balanced
```

**Aggressive** (Higher Risk, Loose Thresholds):
```bash
# NAK Controller
python scripts/calibrate_controllers.py --controller nak --profile aggressive

# Dopamine Controller
python scripts/calibrate_controllers.py --controller dopamine --profile aggressive
```

### Validate Configuration
```bash
python scripts/calibrate_controllers.py --validate conf/nak/default.yaml
python scripts/calibrate_controllers.py --validate config/dopamine.yaml
```

### Custom Output Path
```bash
python scripts/calibrate_controllers.py \
  --controller nak \
  --profile balanced \
  --output my_custom_config.yaml
```

## Profile Comparison

| Parameter | Conservative | Balanced | Aggressive |
|-----------|-------------|----------|------------|
| **Risk Level** | Low | Moderate | High |
| **Sensitivity** | Minimal | Standard | High |
| **Thresholds** | Tight | Normal | Loose |
| **Best For** | Low volatility, preservation | Normal markets | High opportunity |

### NAK Controller Differences

| Parameter | Conservative | Balanced | Aggressive |
|-----------|-------------|----------|------------|
| `EI_low` | 0.40 | 0.35 | 0.30 |
| `EI_high` | 0.70 | 0.65 | 0.60 |
| `EI_crit` | 0.20 | 0.15 | 0.10 |
| `vol_amber` | 0.60 | 0.70 | 0.80 |
| `vol_red` | 0.80 | 0.90 | 1.00 |
| `dd_amber` | 0.30 | 0.40 | 0.50 |
| `dd_red` | 0.60 | 0.70 | 0.80 |
| `delta_r_limit` | 0.15 | 0.20 | 0.25 |
| `risk_mult.AMBER` | 0.60 | 0.65 | 0.75 |
| `activity_mult.GREEN` | 1.10 | 1.20 | 1.30 |

### Dopamine Controller Differences

| Parameter | Conservative | Balanced | Aggressive |
|-----------|-------------|----------|------------|
| `learning_rate_v` | 0.05 | 0.10 | 0.15 |
| `burst_factor` | 1.5 | 2.5 | 3.5 |
| `base_temperature` | 0.8 | 1.0 | 1.5 |
| `invigoration_threshold` | 0.80 | 0.75 | 0.65 |
| `no_go_threshold` | 0.30 | 0.25 | 0.15 |

## Typical Workflow

1. **Identify Market Conditions**
   ```bash
   # Check historical volatility and regime
   python scripts/analyze_market_regime.py --data recent_data.csv
   ```

2. **Select Profile**
   - Low volatility, bear market → Conservative
   - Normal conditions → Balanced
   - High volatility, bull market → Aggressive

3. **Apply and Test**
   ```bash
   # Apply profile
   python scripts/calibrate_controllers.py --controller nak --profile balanced
   
   # Validate
   python scripts/calibrate_controllers.py --validate conf/nak/balanced.yaml
   
   # Backtest
   python scripts/run_backtest.py --config conf/nak/balanced.yaml
   ```

4. **Monitor and Iterate**
   - Track Sharpe ratio, drawdown, win rate
   - Adjust parameters if needed
   - Re-validate after changes

## When to Use Each Profile

### Conservative Profile
✅ **Use When:**
- Market volatility is below historical average
- You're in capital preservation mode
- You're new to the system
- Account size is significant relative to risk tolerance

❌ **Avoid When:**
- Strong trending markets with high opportunity
- Need aggressive growth
- Testing new strategies

### Balanced Profile
✅ **Use When:**
- Normal market conditions
- Standard risk tolerance
- Starting point for most users
- General-purpose trading

❌ **Avoid When:**
- Extreme market conditions (very high or very low volatility)
- Need specific risk profile

### Aggressive Profile
✅ **Use When:**
- High volatility with clear trends
- Bull market with strong momentum
- Smaller account size allows for more risk
- Seeking maximum growth

❌ **Avoid When:**
- Market is choppy or ranging
- Capital preservation is priority
- You're uncomfortable with drawdowns

## Validation Checklist

Before deploying any configuration:

- [ ] All validation checks pass
- [ ] Backtest performance meets expectations
- [ ] Parameter relationships are logical (e.g., `EI_low < EI_high`)
- [ ] Risk parameters match your risk tolerance
- [ ] Thresholds align with historical market conditions
- [ ] Paper trading shows stable behavior
- [ ] Monitoring infrastructure is in place

## Troubleshooting

### Issue: Configuration validation fails
```bash
# Check specific validation errors
python scripts/calibrate_controllers.py --validate your_config.yaml

# Common fixes:
# - Ensure EI_low < EI_high
# - Ensure vol_amber <= vol_red
# - Ensure dd_amber <= dd_red
# - Ensure 0 < delta_r_limit <= 1.0
```

### Issue: Too many suspensions
```bash
# Apply more aggressive profile
python scripts/calibrate_controllers.py --controller nak --profile aggressive

# Or manually adjust EI_crit lower
```

### Issue: Excessive drawdowns
```bash
# Apply more conservative profile
python scripts/calibrate_controllers.py --controller nak --profile conservative

# Or manually lower volatility/drawdown thresholds
```

## Advanced Usage

### Custom Profiles
Edit `scripts/calibrate_controllers.py` to add your own profiles:

```python
"my_custom_profile": {
    "description": "Custom profile for specific market conditions",
    "nak": {
        "EI_low": 0.33,
        "EI_high": 0.67,
        # ... other parameters
    },
    "dopamine": {
        "learning_rate_v": 0.12,
        # ... other parameters
    },
}
```

### Parameter Sweeps
For systematic optimization, use the adaptive calibrator:

```python
from tradepulse.core.neuro.adaptive_calibrator import AdaptiveCalibrator

calibrator = AdaptiveCalibrator(initial_params)
# Run optimization loop
```

## Additional Resources

- [Full Calibration Guide](CALIBRATION_GUIDE.md) - Complete documentation
- [NAK Controller Spec](../nak_controller/README.md) - NAK controller details
- [Neuro-Optimization Guide](neuro_optimization_guide.md) - Advanced optimization
- [Dopamine Enhancements](neuromodulators/dopamine_v1_enhancements.md) - Dopamine mechanics

## Support

For questions or issues:
1. Check the [Full Calibration Guide](CALIBRATION_GUIDE.md)
2. Review [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)
3. Open an issue on GitHub with validation output and configuration

---

**Remember**: Always test in backtest and paper trading before live deployment!
