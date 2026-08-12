# Controller Calibration Inventory

Complete inventory of all GeoSync controllers with calibration parameters.

## Summary

| Controller | Parameters | Invariants | Profiles | Status |
|-----------|-----------|-----------|----------|---------|
| NAK | 10+ | 7 | ✅ 3 | Complete |
| Dopamine | 9+ | 8 | ✅ 3 | Complete |
| Serotonin | 17 | 6 | ✅ 3 | Complete |
| Risk Engine | 12+ | 5 | ✅ 3 | Complete |
| Regime Adaptive | 7+ | 4 | ✅ 3 | Complete |
| Rate Limiter | 2 | 2 | 🔄 Planned | Constants defined |
| GABA | 2 | 2 | 🔄 Planned | Constants defined |
| Desensitization | 2 | 2 | 🔄 Planned | Constants defined |

## NAK Controller

**Location**: `nak_controller/`, `src/geosync/core/neuro/nak/`

**Purpose**: Manages neuro-energetic state and trading limits through engagement index monitoring.

**Key Parameters:**
- Engagement Index thresholds (EI_low, EI_high, EI_crit)
- Volatility thresholds (vol_amber, vol_red)
- Drawdown thresholds (dd_amber, dd_red)
- Risk/Activity multipliers by mode (GREEN/AMBER/RED)
- Rate limiting (delta_r_limit)

**Invariants:**
- EI_crit ≤ EI_low < EI_high
- vol_amber ≤ vol_red
- dd_amber ≤ dd_red
- 0 < delta_r_limit ≤ 1.0

**Profiles Available:** Conservative, Balanced, Aggressive

**Configuration Files:**
- `conf/nak/conservative.yaml`
- `conf/nak/balanced.yaml`
- `conf/nak/aggressive.yaml`

## Dopamine Controller

**Location**: `src/geosync/core/neuro/dopamine/`

**Purpose**: Implements reward prediction error (RPE) and action selection with exploration/exploitation balance.

**Key Parameters:**
- Learning rates (learning_rate_v, discount_gamma)
- Burst amplification (burst_factor)
- Temperature (base_temperature, min_temperature)
- Gate thresholds (invigoration_threshold, no_go_threshold, hold_threshold)
- Decay rates

**Invariants:**
- 0 < discount_gamma < 1.0
- learning_rate_v > 0
- burst_factor ≥ 1.0
- min_temperature ≤ base_temperature
- All gate thresholds in [0, 1]

**Profiles Available:** Conservative, Balanced, Aggressive

**Configuration Files:**
- `config/profiles/dopamine_conservative.yaml`
- `config/profiles/dopamine_balanced.yaml`
- `config/profiles/dopamine_aggressive.yaml`

## Serotonin Controller

**Location**: `src/geosync/core/neuro/serotonin/`

**Purpose**: Models chronic stress dynamics and produces hold decisions for the trading system.

**Key Parameters:**
- Stress thresholds (stress_threshold, release_threshold)
- Hysteresis (hysteresis)
- EMA decay rates (tonic_beta, phasic_beta)
- Gain factors (stress_gain, drawdown_gain, novelty_gain)
- Cooldown (cooldown_ticks, cooldown_extension)
- Desensitization (desensitization_rate, max_desensitization)
- Temperature floor (floor_min, floor_max, floor_gain)

**Invariants:**
- release_threshold ≤ stress_threshold
- 0 ≤ tonic_beta, phasic_beta ≤ 1.0
- floor_min ≤ floor_max
- max_desensitization < 1.0

**Profiles Available:** Conservative, Balanced, Aggressive

**Configuration Files:**
- `configs/serotonin_conservative.yaml`
- `configs/serotonin_balanced.yaml`
- `configs/serotonin_aggressive.yaml`

## Risk Engine

**Location**: `geosync/risk/`, `execution/risk/`

**Purpose**: Enforces hard limits to protect capital through position, notional, and rate limits.

**Key Parameters:**
- Loss limits (max_daily_loss, max_daily_loss_percent)
- Position limits (max_position_size_default, max_notional_per_order)
- Leverage (max_leverage)
- Rate limits (max_orders_per_minute, max_orders_per_hour)
- Kill-switch (kill_switch_loss_threshold, kill_switch_loss_streak)
- Safe mode (safe_mode_position_multiplier)

**Invariants:**
- 0 < max_daily_loss_percent ≤ 1.0
- max_leverage > 0
- max_orders_per_minute ≤ max_orders_per_hour
- 0 ≤ safe_mode_position_multiplier ≤ 1.0
- kill_switch_loss_streak ≥ 1

**Profiles Available:** Conservative, Balanced, Aggressive

**Configuration Files:**
- `configs/risk_engine_conservative.yaml`
- `configs/risk_engine_balanced.yaml`
- `configs/risk_engine_aggressive.yaml`

## Regime Adaptive Guard

**Location**: `execution/risk/advanced.py` (RegimeAdaptiveExposureGuard)

**Purpose**: Dynamically scales exposure allowances based on realized volatility regimes.

**Key Parameters:**
- Regime thresholds (calm_threshold, stressed_threshold, critical_threshold)
- Exposure multipliers (calm_multiplier, stressed_multiplier, critical_multiplier)
- EWMA parameters (half_life_seconds, min_samples)
- Cooldown (cooldown_seconds)

**Invariants:**
- calm_threshold < stressed_threshold < critical_threshold
- All multipliers > 0
- half_life_seconds > 0
- min_samples ≥ 1

**Profiles Available:** Conservative, Balanced, Aggressive

**Configuration Files:**
- `configs/regime_adaptive_conservative.yaml`
- `configs/regime_adaptive_balanced.yaml`
- `configs/regime_adaptive_aggressive.yaml`

## Rate Limiter

**Location**: `application/api/rate_limit.py`, `execution/risk/core.py`

**Purpose**: Sliding window rate limiter for API endpoints and order submission.

**Key Parameters:**
- Limit (limit) - Maximum requests in window
- Window duration (window_seconds)

**Invariants:**
- limit ≥ 1
- window_seconds > 0

**Profiles Available:** Not yet (constants defined)

**Usage Context:**
- API request throttling
- Order submission rate limiting
- Exchange compliance

## GABA Controller

**Location**: `modules/gaba_inhibition_gate.py`, `src/geosync/core/neuro/gaba/`

**Purpose**: Provides inhibitory control to prevent impulsive actions.

**Key Parameters:**
- Impulse detection (impulse_threshold)
- Inhibition strength (inhibition_strength)

**Invariants:**
- impulse_threshold ≥ 0
- 0 ≤ inhibition_strength ≤ 1.0

**Profiles Available:** Not yet (constants defined)

**Usage Context:**
- Preventing overtrading
- Impulse control in volatile conditions
- Risk mitigation

## Desensitization

**Location**: `src/geosync/core/neuro/desensitization/`

**Purpose**: Manages receptor desensitization under repeated stimulation.

**Key Parameters:**
- Sensitivity bounds (min_sensitivity, max_sensitivity)
- Decay rate (decay_rate)

**Invariants:**
- min_sensitivity ≤ max_sensitivity
- Both in (0, 1]
- decay_rate ≥ 0

**Profiles Available:** Not yet (constants defined)

**Usage Context:**
- Signal adaptation
- Preventing overfitting to noise
- Habituation to repeated patterns

## Magic Numbers Eliminated

All hardcoded thresholds and parameters have been moved to `core/neuro/calibration_constants.py`:

**Before:**
```python
# Scattered magic numbers
if volatility > 0.90:  # RED threshold
    risk_multiplier = 0.0
elif volatility > 0.70:  # AMBER threshold
    risk_multiplier = 0.65
```

**After:**
```python
from core.neuro.calibration_constants import NAKParameterRanges

ranges = NAKParameterRanges()
if volatility > ranges.VOL_RED_DEFAULT:
    risk_multiplier = ranges.RISK_MULT_RED_DEFAULT
elif volatility > ranges.VOL_AMBER_DEFAULT:
    risk_multiplier = ranges.RISK_MULT_AMBER_DEFAULT
```

## Validation System

All controllers use centralized validation:

```python
from core.neuro.calibration_constants import validate_parameter_invariants

# Validate any controller
params = {"EI_low": 0.35, "EI_high": 0.65, "EI_crit": 0.15}
is_valid, errors = validate_parameter_invariants("nak", params)

if not is_valid:
    for error in errors:
        print(f"Validation error: {error}")
```

**Benefits:**
- Consistent validation across all controllers
- Clear error messages with parameter names and values
- Single point of maintenance
- Prevents invalid configurations at runtime

## Testing Coverage

Total test cases: **60+**

- Parameter range consistency: 5 tests
- NAK invariants: 7 tests
- Dopamine invariants: 7 tests
- Serotonin invariants: 6 tests
- Risk Engine invariants: 6 tests
- Regime Adaptive invariants: 5 tests
- Other controllers: 6 tests
- Profile validation: 15+ tests

All tests in:
- `tests/core/neuro/test_calibration_constants.py`
- `tests/scripts/test_calibrate_controllers.py`

## Usage

### CLI Usage

```bash
# List profiles
python scripts/calibrate_controllers.py --list-profiles

# Apply profile
python scripts/calibrate_controllers.py --controller nak --profile balanced

# Validate config
python scripts/calibrate_controllers.py --validate conf/nak/default.yaml
```

### Makefile Usage

```bash
make calibrate-list           # List profiles
make calibrate-validate       # Validate configs
make calibrate-balanced       # Apply balanced to all
```

### Programmatic Usage

```python
from core.neuro.calibration_constants import NAKParameterRanges

ranges = NAKParameterRanges()
ei_low = ranges.EI_LOW_DEFAULT
ei_high = ranges.EI_HIGH_DEFAULT
```

## Future Enhancements

### Planned

1. **Dynamic Calibration**: Auto-adjust based on performance metrics
2. **Per-Asset Profiles**: Different calibrations for different symbols
3. **A/B Testing**: Compare profile performance
4. **ML-Based Tuning**: Learn optimal parameters from historical data
5. **Profile Interpolation**: Generate intermediate profiles
6. **Real-time Monitoring**: Dashboard for parameter effectiveness

### Adding New Controllers

To add a new controller to the calibration system:

1. Define parameter ranges in `calibration_constants.py`
2. Add validation function
3. Register in `validate_parameter_invariants()`
4. Add profiles in `calibrate_controllers.py`
5. Create tests in `test_calibration_constants.py`
6. Update documentation

## See Also

- [CALIBRATION_GUIDE.md](../CALIBRATION_GUIDE.md) - Complete calibration guide
- [CALIBRATION_PARAMETER_REFERENCE.md](../CALIBRATION_PARAMETER_REFERENCE.md) - Detailed parameter tables
- [calibration_constants.py](../../core/neuro/calibration_constants.py) - Source code
- [calibrate_controllers.py](../../scripts/calibrate_controllers.py) - CLI tool
