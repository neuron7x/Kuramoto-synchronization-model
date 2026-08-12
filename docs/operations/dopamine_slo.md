# Dopamine SLI/SLO Surface

The dopamine component is operationally ready only when correctness is observable as deterministic local metrics.

Required SLIs:

- `dopamine.rpe_finite_rate`
- `dopamine.output_finite_rate`
- `dopamine.output_bound_violation_count`
- `dopamine.config_validation_pass_rate`
- `dopamine.schema_runtime_parity_failures`
- `dopamine.contract_violation_count`
- `dopamine.null_survival_rate`
- `dopamine.artifact_completeness_rate`
- `dopamine.claim_promotion_block_count`
- `dopamine.backtest_parity_error_rate`
- `dopamine.p95_step_latency_ms`
- `dopamine.p99_step_latency_ms`
- `dopamine.max_memory_mb`

SLO defaults for gates: finite rates equal `1.0`, violation counts equal `0`, artifact completeness equals `1.0`, and invalid claim-promotion fixtures must be blocked at least once.
