# SerotoninController v2.3.1 — Falsification Plan

## H₀₁: Smooth Phasic Gate Provides No Benefit
- **Claim:** Replacing the binary phase switch with a smooth logistic gate does *not* reduce false positive trade entries during volatility spikes.
- **Test Protocol:** Run the 2024-2025 high-volatility replay with identical seeds across v2.2 and v2.3.1. Flag false entries as trades initiated within 3 ticks before a >2σ drawdown reversal. Use matched-pairs t-test on entry counts per episode.
- **Rejection Criterion:** Reject H₀₁ if v2.3.1 reduces mean false entries by ≥10% with p < 0.05.

## H₀₂: Exponential Desensitisation Fails to Thaw Chronic HOLD States
- **Claim:** The new sensitivity decay `exp(-sig / 12)` with capped counters does *not* reduce the proportion of HOLD-dominated sessions during 20-day stress phases.
- **Test Protocol:** Execute the 2022 bear-market backtest (rolling 20-day windows). Measure proportion of sessions where HOLD actions exceed 80% of ticks. Compare distributions with Mann–Whitney U test versus v2.2.
- **Rejection Criterion:** Reject H₀₂ if v2.3.1 lowers the HOLD-heavy session ratio by ≥25% with U-test p < 0.05.

## H₀₃: Time-Scaled Meta-Adaptation and TACL Guard Do Not Improve Risk Efficiency
- **Claim:** Introducing tick-duration-aware modulation and the TACL guard fails to improve Sharpe-to-drawdown efficiency in out-of-sample (OOS) evaluation.
- **Test Protocol:** Run 6-month OOS simulations (2025 H1 analog). Compute Sharpe/|DD| for v2.2 and v2.3.1 with identical randomness. Ensure guard is active (rejecting proposals that increase free energy). Apply paired bootstrap (10k samples) on Sharpe/|DD| differences.
- **Rejection Criterion:** Reject H₀₃ if the median Sharpe/|DD| uplift ≥5% and the 95% bootstrap CI of the uplift is entirely >0.

## Reporting
- Track telemetry: `serotonin_tonic_level`, `serotonin_phasic_level`, `serotonin_gate_level`, `serotonin_sensitivity`, `serotonin_level`, `serotonin_alpha_drift`, `serotonin_beta_drift`, `serotonin_gamma_drift`.
- Record guard decisions via `serotonin_cooldown_guard{controller_version="v2.3.1"}` and `serotonin_meta_adapt_guard{controller_version="v2.3.1"}`.
- Archive replay manifests, seeds, and statistical summaries in `reports/neuro/serotonin/v2_3_1/`.
- If any null hypothesis cannot be rejected, regress to v2.2 parameters or iterate with revised gating/desensitisation constants before production rollout.
