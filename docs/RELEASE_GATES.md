# Progressive Release Gates

The Progressive Rollout pipeline promotes builds through a sequence of quality
and safety gates before traffic reaches production.  The gates are orchestrated
by the GitHub Actions workflow `progressive-release-gates.yml` and a lightweight
Python harness (`tacl.release_gates`).

## Gates and Thresholds

1. **Latency Gate** – uses `observability.release_gates.ReleaseGateEvaluator`
   with the following thresholds (milliseconds):
   - median ≤ 60
   - p95 ≤ 85
   - max ≤ 120
2. **Coverage Gate** – requires the test suite to report coverage ≥ 0.92.  The
   observed coverage is read from `ci/release_gates.yml`.
3. **Performance Budget Gate** – asserts that each component listed in
   `configs/perf_budgets.yaml` stays within its budget.  Budgets are expressed in
   milliseconds measured by the synthetic benchmark harness.
4. **Energy Regression Gate** – reuses the TACL validator to ensure the selected
   scenario stays under the free energy limit (1.35).  Negative scenarios must
   fail validation; otherwise the job fails loudly to prevent silent regressions.

## Metrics Sources

- Latency samples originate from the link activator replay harness and are
  recorded in `ci/release_gates.yml`.
- Coverage data comes from the merged coverage report published by the test
  pipeline.
- Performance metrics come from the offline benchmark runner that writes the
  latest observations into `configs/perf_budgets.yaml`.
- Energy metrics reuse the same fixtures as the thermodynamic validation step
  (`tacl/link_activator_test_scenarios.yaml`).

## Failure Semantics

When any gate fails the workflow emits structured artifacts in
`.ci_artifacts/release_gates.json` and `.ci_artifacts/release_gates.md`.
These artifacts contain:

- the failing gate name and human-readable reason,
- the raw metrics (latency percentiles, coverage figures, performance samples),
- the computed free energy and entropy for energy failures,
- the outcome of the negative test scenarios.

The workflow exits with code **1** and the Progressive Rollout pipeline halts in
place.  Operators should consult `docs/OPERATIONS.md` for remediation guidance.
