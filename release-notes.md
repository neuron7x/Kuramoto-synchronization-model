# Release Notes

## Thermodynamic Validation Hotfix
- Fixed weight normalisation in the TACL energy model to prevent false
  positives in the `validate-energy` workflow.
- Added regression unit tests and end-to-end rollout simulations capturing the
  automated rollback flow when free energy exceeds 1.35.
- Hardened Progressive Release Gates with deterministic artifacts and explicit
  performance budgets sourced from `configs/perf_budgets.yaml`.
