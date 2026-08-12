# Stage 2A — Coverage Surface Contract Foundation

## Stage 2A scope
Stage 2A introduces the contract layer for coverage governance: surfaces, thresholds, mapping rules, and a validator CLI.

## What this PR does
- Defines `configs/quality/coverage_targets.toml` for coverage surfaces and thresholds.
- Adds `tools/coverage/surface_contract.py` for strict surface mapping and contract validation.
- Adds `tools/coverage/validate_coverage_targets.py` CLI for contract validation and unmapped-file reporting.
- Adds unit tests for contract and CLI behavior.
- Adds governance boundary updates in `docs/METRICS_CONTRACT.md`.

## What this PR explicitly does not do
- Does not generate or validate real coverage percentages.
- Does not add backtest edge-case tests.
- Does not add execution negative-path tests.
- Does not add Stage 2 diff-coverage CI gate enforcement.
- Does not promote coverage claims to `proven`.

## Coverage surface model
Surfaces are path-scoped domains: `core`, `backtest`, `execution`, `analytics`, `ingestion`, and `risk`. Mapping is deterministic prefix matching. Unmapped files are reported explicitly.

## Target threshold model
Each surface has `short_term`, `mid_term`, `final`, `claim_risk`, and `rationale`. The validator enforces threshold order (`short_term <= mid_term <= final`) and numeric range bounds.

## How to run validation
```bash
python tools/coverage/validate_coverage_targets.py \
  --targets configs/quality/coverage_targets.toml
```

Optional mapping report:
```bash
python tools/coverage/validate_coverage_targets.py \
  --targets configs/quality/coverage_targets.toml \
  --files changed_files.txt \
  --json-out reports/coverage/coverage_target_validation.json
```

## Claim boundary
“Stage 2A defines the coverage surface contract. It does not prove that coverage thresholds are currently met.”

## Next PR sequence
- Stage 2B: coverage XML parser, summary generator, module_coverage.json, and priority map
- Stage 2C: execution negative-path tests
- Stage 2D: backtest edge-case tests
- Stage 2E: diff coverage CI gate and artifact upload
- Stage 2F: METRICS_CONTRACT promotion only if artifacts support it
