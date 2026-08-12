---
owner: quant-systems@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Calibration Parameter Reference

Comprehensive reference for all calibration parameters across GeoSync controllers.

## Table of Contents

1. [NAK Controller](#nak-controller)
2. [Dopamine Controller](#dopamine-controller)
3. [Serotonin Controller](#serotonin-controller)
4. [Risk Engine](#risk-engine)
5. [Regime Adaptive Guard](#regime-adaptive-guard)
6. [Rate Limiter](#rate-limiter)
7. [GABA Controller](#gaba-controller)
8. [Desensitization](#desensitization)
9. [Quick Reference Tables](#quick-reference-tables)

## NAK Controller

The NAK (Neuro-Arousal-Ketosis) Controller manages energy, load, and engagement to determine trading activity levels.

### Engagement Index Thresholds

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `EI_low` | 0.0-1.0 | 0.40 | 0.35 | 0.30 | Lower bound of normal engagement band |
| `EI_high` | 0.0-1.0 | 0.70 | 0.65 | 0.60 | Upper bound of normal engagement band |
| `EI_crit` | 0.0-1.0 | 0.20 | 0.15 | 0.10 | Critical threshold (below = suspend) |
| `EI_hysteresis` | 0.0-0.2 | - | 0.05 | - | Hysteresis for unsuspend threshold |

**Invariants:**
- `EI_crit` ≤ `EI_low` < `EI_high`
- All values in [0.0, 1.0]

**Tuning Guidance:**
- Wider bands (larger `EI_high - EI_low`) = more stable operation
- Lower `EI_crit` = more aggressive (harder to suspend)
- Higher hysteresis = more stable (less flip-flopping)

### Volatility and Drawdown Thresholds

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `vol_amber` | 0.0-2.0 | 0.60 | 0.70 | 0.80 | Volatility threshold for AMBER mode |
| `vol_red` | 0.0-2.0 | 0.80 | 0.90 | 1.00 | Volatility threshold for RED mode |
| `dd_amber` | 0.0-1.0 | 0.30 | 0.40 | 0.50 | Drawdown threshold for AMBER mode |
| `dd_red` | 0.0-1.0 | 0.60 | 0.70 | 0.80 | Drawdown threshold for RED mode |

**Invariants:**
- `vol_amber` ≤ `vol_red`
- `dd_amber` ≤ `dd_red`

**Tuning Guidance:**
- Lower thresholds = more conservative (enter protective modes earlier)
- Larger gaps between AMBER and RED = smoother transitions
- Match to your historical volatility and drawdown tolerance

### Risk and Activity Multipliers

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `risk_mult.GREEN` | 0.0-3.0 | 1.00 | 1.00 | 1.00 | Risk multiplier in normal mode |
| `risk_mult.AMBER` | 0.0-3.0 | 0.60 | 0.65 | 0.75 | Risk multiplier in elevated risk mode |
| `risk_mult.RED` | 0.0-3.0 | 0.00 | 0.00 | 0.00 | Risk multiplier in high risk mode |
| `activity_mult.GREEN` | 0.0-3.0 | 1.10 | 1.20 | 1.30 | Activity multiplier in normal mode |
| `activity_mult.AMBER` | 0.0-3.0 | 0.85 | 0.90 | 1.00 | Activity multiplier in elevated risk |
| `activity_mult.RED` | 0.0-3.0 | 0.50 | 0.60 | 0.70 | Activity multiplier in high risk mode |

**Invariants:**
- All multipliers ≥ 0

**Tuning Guidance:**
- `GREEN` multipliers > 1.0 encourage activity in good conditions
- `AMBER` multipliers < 1.0 reduce exposure in moderate stress
- `RED` typically suspends all activity (`risk_mult.RED = 0`)

### Rate Limiting

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `delta_r_limit` | (0.0, 1.0] | 0.15 | 0.20 | 0.25 | Maximum rate of change in risk factor |

**Invariants:**
- 0 < `delta_r_limit` ≤ 1.0

---

## Dopamine Controller

The Dopamine Controller implements reward prediction error (RPE) and action selection with exploration/exploitation balance.

### Learning and Adaptation

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `learning_rate_v` | (0.0, 1.0] | 0.05 | 0.10 | 0.15 | Value function learning rate |
| `discount_gamma` | (0.0, 1.0) | - | 0.98 | - | Future reward discount factor |
| `burst_factor` | [1.0, 10.0] | 1.5 | 2.5 | 3.5 | Phasic dopamine amplification |
| `decay_rate` | [0.0, 1.0] | - | 0.95 | - | Tonic level EMA decay rate |

**Invariants:**
- 0 < `discount_gamma` < 1.0
- `learning_rate_v` > 0
- `burst_factor` ≥ 1.0

**Tuning Guidance:**
- Higher `learning_rate_v` = faster adaptation but less stability
- Higher `discount_gamma` = more long-term oriented
- Higher `burst_factor` = stronger reactions to unexpected rewards

### Exploration and Temperature

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `base_temperature` | (0.0, 5.0] | 0.8 | 1.0 | 1.5 | Exploration temperature |
| `min_temperature` | [0.0, 5.0] | - | 0.05 | - | Minimum temperature floor |
| `neg_rpe_temp_gain` | [0.0, 2.0] | - | 0.5 | - | Extra exploration after losses |

**Invariants:**
- `base_temperature` > 0
- `min_temperature` ≤ `base_temperature`

**Tuning Guidance:**
- Higher temperature = more exploration, less exploitation
- Lower minimum = can become very deterministic
- Higher RPE gain = more recovery attempts after losses

### Gating Thresholds

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `invigoration_threshold` | [0.0, 1.0] | 0.80 | 0.75 | 0.65 | Threshold for GO activation |
| `no_go_threshold` | [0.0, 1.0] | 0.30 | 0.25 | 0.15 | Threshold for NO-GO inhibition |
| `hold_threshold` | [0.0, 1.0] | - | 0.40 | - | Threshold for HOLD signal |

**Invariants:**
- All thresholds in [0.0, 1.0]

**Tuning Guidance:**
- Lower GO threshold = more aggressive entry
- Higher NO-GO threshold = easier to block trades
- Adjust based on false positive/negative analysis

---

## Serotonin Controller

The Serotonin Controller models chronic stress dynamics and produces hold decisions.

### Stress Management

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `stress_threshold` | [0.0, 1.5] | 0.70 | 0.80 | 0.90 | Level above which hold state is entered |
| `release_threshold` | [0.0, stress_threshold] | 0.45 | 0.50 | 0.55 | Level below which hold state is released |
| `hysteresis` | [0.0, 1.0] | 0.15 | 0.10 | 0.08 | Hysteresis band for transitions |
| `stress_gain` | ≥ 0.0 | 0.8 | 1.0 | 1.2 | Multiplier for stress input |

**Invariants:**
- `release_threshold` ≤ `stress_threshold`
- 0 ≤ `stress_threshold` ≤ 1.5
- 0 ≤ `hysteresis` ≤ 1.0

**Tuning Guidance:**
- Lower thresholds = more conservative (easier to enter hold)
- Higher hysteresis = more stability in mode transitions
- Higher stress gain = more responsive to stress signals

### Adaptation Parameters

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `cooldown_ticks` | ≥ 0 | 8 | 5 | 3 | Minimum ticks in cooldown after hold exit |
| `tonic_beta` | [0.0, 1.0] | - | 0.95 | - | EMA decay for tonic (slow) integration |
| `phasic_beta` | [0.0, 1.0] | - | 0.70 | - | EMA decay for phasic (fast) response |

**Invariants:**
- `cooldown_ticks` ≥ 0
- Betas in [0.0, 1.0]

---

## Risk Engine

The Risk Engine enforces hard limits to protect capital.

### Loss Limits

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `max_daily_loss` | ≥ 0.0 | - | 10000.0 | - | Absolute daily loss limit (currency) |
| `max_daily_loss_percent` | (0.0, 1.0] | 0.03 | 0.05 | 0.08 | Daily loss limit (fraction of equity) |

**Invariants:**
- 0 < `max_daily_loss_percent` ≤ 1.0

**Tuning Guidance:**
- Set based on your risk tolerance and account size
- Conservative: 3% max daily loss
- Balanced: 5% max daily loss
- Aggressive: 8% max daily loss

### Position and Leverage Limits

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `max_position_size_default` | ≥ 0.0 | - | 100.0 | - | Default max position size per symbol |
| `max_notional_per_order` | ≥ 0.0 | - | 100000.0 | - | Maximum notional value per order |
| `max_leverage` | > 0.0 | 3.0 | 5.0 | 8.0 | Maximum portfolio leverage |

**Invariants:**
- `max_leverage` > 0

**Tuning Guidance:**
- Lower leverage = more conservative
- Set position limits based on liquidity and volatility
- Consider regulatory requirements

### Kill Switch and Safe Mode

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `kill_switch_loss_threshold` | ≥ 0.0 | - | 25000.0 | - | Loss triggering kill-switch |
| `kill_switch_loss_streak` | ≥ 1 | 3 | 5 | 7 | Consecutive losses triggering switch |
| `safe_mode_position_multiplier` | [0.0, 1.0] | 0.20 | 0.25 | 0.30 | Position multiplier in safe mode |

**Invariants:**
- `kill_switch_loss_streak` ≥ 1
- 0 ≤ `safe_mode_position_multiplier` ≤ 1.0

**Tuning Guidance:**
- Lower streak = more sensitive kill-switch
- Lower multiplier = more conservative safe mode
- Balance between protection and operational continuity

### Rate Limits

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `max_orders_per_minute` | ≥ 0 | - | 60 | - | Order rate limit per minute |
| `max_orders_per_hour` | ≥ 0 | - | 500 | - | Order rate limit per hour |

**Invariants:**
- `max_orders_per_minute` ≤ `max_orders_per_hour`

---

## Regime Adaptive Guard

Dynamically scales exposure allowances based on realized volatility regimes.

### Volatility Regime Thresholds

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `calm_threshold` | (0.001, 0.1) | 0.004 | 0.005 | 0.006 | Absolute return for CALM regime |
| `stressed_threshold` | (0.001, 0.1) | 0.018 | 0.020 | 0.025 | Absolute return for STRESSED regime |
| `critical_threshold` | (0.001, 0.1) | 0.035 | 0.040 | 0.050 | Absolute return for CRITICAL regime |

**Invariants:**
- `calm_threshold` < `stressed_threshold` < `critical_threshold`

**Tuning Guidance:**
- Based on historical volatility analysis
- Lower thresholds = more sensitive regime detection
- Match to your asset's typical volatility characteristics

### Exposure Multipliers

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `calm_multiplier` | > 0.0 | 1.05 | 1.10 | 1.15 | Exposure multiplier in calm markets |
| `normal_multiplier` | - | 1.00 | 1.00 | 1.00 | Baseline (always 1.0) |
| `stressed_multiplier` | > 0.0 | 0.60 | 0.65 | 0.70 | Exposure multiplier in stressed markets |
| `critical_multiplier` | > 0.0 | 0.35 | 0.40 | 0.45 | Exposure multiplier in critical regime |

**Invariants:**
- All multipliers > 0

**Tuning Guidance:**
- Calm multipliers > 1.0 = take advantage of low volatility
- Stressed/critical multipliers < 1.0 = reduce exposure in stress
- More aggressive profiles have less dramatic reductions

### Adaptation Parameters

| Parameter | Range | Conservative | Balanced | Aggressive | Description |
|-----------|-------|--------------|----------|------------|-------------|
| `half_life_seconds` | > 0.0 | - | 120.0 | - | EWMA half-life for volatility estimate |
| `min_samples` | ≥ 1 | - | 5 | - | Minimum samples before regime detection |
| `cooldown_seconds` | ≥ 0.0 | - | 30.0 | - | Cooldown after regime downgrade |

**Invariants:**
- `half_life_seconds` > 0
- `min_samples` ≥ 1

---

## Rate Limiter

Sliding window rate limiter for API endpoints and order submission.

### Parameters

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| `limit` | ≥ 1 | 100 | Maximum requests in window |
| `window_seconds` | > 0.0 | 60.0 | Sliding window duration |

**Invariants:**
- `limit` ≥ 1
- `window_seconds` > 0

**Tuning Guidance:**
- Match to exchange/API rate limits
- Add buffer for safety (use 80-90% of actual limit)
- Consider burst patterns in your strategy

---

## GABA Controller

Provides inhibitory control to prevent impulsive actions.

### Parameters

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| `impulse_threshold` | ≥ 0.0 | 0.7 | Threshold for impulse detection |
| `inhibition_strength` | [0.0, 1.0] | 0.5 | Strength of inhibitory signal |

**Invariants:**
- `impulse_threshold` ≥ 0
- 0 ≤ `inhibition_strength` ≤ 1.0

**Tuning Guidance:**
- Lower threshold = more sensitive to impulses
- Higher strength = stronger inhibition
- Balance between protection and responsiveness

---

## Desensitization

Manages receptor desensitization under repeated stimulation.

### Parameters

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| `min_sensitivity` | (0.0, 1.0] | 0.3 | Minimum sensitivity level |
| `max_sensitivity` | (0.0, 1.0] | 1.0 | Maximum sensitivity level |
| `decay_rate` | ≥ 0.0 | 0.01 | Desensitization decay rate |

**Invariants:**
- `min_sensitivity` ≤ `max_sensitivity`
- Both in (0.0, 1.0]
- `decay_rate` ≥ 0

**Tuning Guidance:**
- Lower min_sensitivity = more desensitization possible
- Higher decay rate = faster desensitization
- Match to your signal update frequency

---

## Quick Reference Tables

### Profile Comparison: Risk Tolerance

| Controller | Metric | Conservative | Balanced | Aggressive |
|-----------|--------|--------------|----------|------------|
| NAK | EI_crit | 0.20 (hard to trade) | 0.15 (moderate) | 0.10 (easy to trade) |
| NAK | vol_red | 0.80 (tight) | 0.90 (moderate) | 1.00 (loose) |
| Dopamine | learning_rate | 0.05 (slow) | 0.10 (moderate) | 0.15 (fast) |
| Serotonin | stress_threshold | 0.70 (low) | 0.80 (moderate) | 0.90 (high) |
| Risk Engine | max_daily_loss% | 3% | 5% | 8% |
| Risk Engine | max_leverage | 3.0x | 5.0x | 8.0x |
| Regime Adaptive | stressed_multiplier | 0.60 (cautious) | 0.65 (moderate) | 0.70 (bold) |

### Invariant Quick Check

Use this checklist to validate any custom configuration:

- [ ] NAK: `EI_crit` ≤ `EI_low` < `EI_high`
- [ ] NAK: `vol_amber` ≤ `vol_red`
- [ ] NAK: `dd_amber` ≤ `dd_red`
- [ ] Dopamine: 0 < `discount_gamma` < 1.0
- [ ] Dopamine: `min_temperature` ≤ `base_temperature`
- [ ] Serotonin: `release_threshold` ≤ `stress_threshold`
- [ ] Serotonin: `floor_min` ≤ `floor_max`
- [ ] Risk Engine: 0 < `max_daily_loss_percent` ≤ 1.0
- [ ] Risk Engine: `max_orders_per_minute` ≤ `max_orders_per_hour`
- [ ] Regime Adaptive: `calm_threshold` < `stressed_threshold` < `critical_threshold`

### Default Values Reference

| Controller | Critical Parameters | Default Values |
|-----------|---------------------|----------------|
| NAK | EI_low, EI_high, EI_crit | 0.35, 0.65, 0.15 |
| Dopamine | learning_rate_v, burst_factor | 0.10, 2.5 |
| Serotonin | stress_threshold, release_threshold | 0.80, 0.50 |
| Risk Engine | max_daily_loss%, max_leverage | 0.05 (5%), 5.0x |
| Regime Adaptive | calm, stressed, critical | 0.005, 0.020, 0.040 |

---

## See Also

- [CALIBRATION_GUIDE.md](CALIBRATION_GUIDE.md) - Complete calibration process guide
- [CALIBRATION_QUICK_START.md](CALIBRATION_QUICK_START.md) - Quick start for common scenarios
- [calibration_constants.py](../core/neuro/calibration_constants.py) - Source code reference
