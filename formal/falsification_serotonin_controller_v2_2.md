# Falsification Hypotheses — SerotoninController v2.2

## 1. Dynamic Tonic vs Static Baseline
- **Hypothesis:** The tonic filter (decay_rate = 0.05) reaches cooldown (>0.7 serotonin) at least 15% faster than a static release baseline during volatility spikes.
- **Test:** Simulate a burst volatility profile (0.1 → 2.0 within five ticks) and compare ticks-to-threshold between v2.2 and a static tonic baseline.
- **Falsification:** If v2.2 does not achieve a ≥15% faster cooldown trigger, reject the tonic filter improvement claim.

## 2. Desensitisation vs Frozen Behaviour
- **Hypothesis:** Sensitivity adaptation with a 0.01 rate and 100 tick onset reduces frozen HOLD days (>80% HOLD actions) by ≥30% under 14-day high-volatility streaks.
- **Test:** Backtest a 2022 bear market segment; measure HOLD dominance days for v2.2 versus a model without desensitisation.
- **Falsification:** If frozen days are not reduced by ≥30%, discard the desensitisation mechanism benefit.

## 3. Meta-Adaptation vs Static Weights
- **Hypothesis:** Meta-adaptation improves out-of-sample Sharpe/|DD| by ≥5% over six months compared to static release weights.
- **Test:** Run a 2025 H1 out-of-sample evaluation with and without meta-adaptation, tracking Sharpe and maximum drawdown.
- **Falsification:** If improvements are ≤0%, reject meta-adaptation as ineffective.

## 4. Risk-Regime Robustness
- **Hypothesis:** Parameter robustness improves, yielding lower Sharpe and drawdown variance under ±10% configuration noise relative to v2.1.
- **Test:** Sample 100 configurations within ±10% weight perturbations, evaluate on a shared dataset, and compute variance.
- **Falsification:** If variance is not reduced, the robustness claim fails.

## 5. Validation Impact
- **Hypothesis:** Input validation and counter caps eliminate runtime crashes on invalid data without degrading valid performance.
- **Test:** Inject negative inputs to confirm ValueError paths, then compare baseline metrics between v2.2 and v2.1 on valid data.
- **Falsification:** If runtime crashes persist or performance diverges materially, reject the validation improvements.
