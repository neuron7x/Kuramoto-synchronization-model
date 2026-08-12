# Quality Gates and Automated Governance

Quality gates prevent regressions from entering `main` by enforcing measurable
criteria across testing, performance, and reliability domains.

## Developer Pre-Commit Stack

- **Ruff, Black, MyPy, Slotscheck** – Install the pre-commit suite defined in
  [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) to lint, format, type
  check, and verify `__slots__` coverage before pushing. The configuration pins
  `slotscheck==0.19.1`, ensuring that object layouts stay compact and that
  inheritance hierarchies remain compatible with slots-enabled classes.
- **Installation** – Run `pre-commit install` after syncing
  [`requirements-dev.txt`](../requirements-dev.txt) so all hooks execute locally
  on staged files. CI runs the same hooks to maintain parity.

## Pull Request Blocking Rules

1. **Code Coverage** – PRs fail if overall coverage drops by more than 0.5% or
   critical packages fall below 85%. Coverage deltas are computed against the
   baseline stored in `reports/coverage-baseline.json`.
2. **Performance Budget** – Frontend builds must satisfy the budgets defined in
   `docs/performance.md`. Lighthouse CI asserts route-level LCP/TTFB, while the
   bundle-size bot compares asset weights with the previous successful build.
3. **Latency SLOs** – Synthetic smoke tests replay key execution flows. If the
   SLI dashboards predict burn-rate exhaustion under 72 hours, the PR merge is
   blocked until mitigations land.
4. **Heavy-math validation** – Dedicated jobs defined in
   `configs/quality/heavy_math_jobs.yaml` execute Kuramoto, Ricci, and Hurst
   stress workloads with enforced CPU/memory quotas. The jobs run under the
   `heavy_math` pytest marker and must pass before a PR can merge.
5. **Cross-architecture parity** – Indicator portability tests labelled with the
   `arm` marker compare CPU, GPU, and float32 (ARM-simulated) execution paths.
   CI requires parity within ±0.005 absolute tolerance; deviations block the
   pipeline and page the platform quality channel.

## Nightly Benchmarks and Auto-Triage

- Nightly benchmark jobs compare runtime metrics (execution latency, backtest
  throughput, ingestion lag) to the last green build.
- When degradation exceeds configured thresholds (default 5%), the pipeline:
  - Adds an `auto-regression` label to the offending PR if identified.
  - Creates a Jira task in the `Reliability` project assigned to the owning team.
  - Posts a summary to `#eng-quality` including CLI artifact hashes for the run.

## Workflow for Exceptions

1. Engineer raises an exception request with justification, impact analysis, and
   expiry date.
2. Quality lead reviews and, if approved, records the exception in
   `configs/quality/exceptions.yaml` with a maximum lifetime of 14 days.
3. CI pipelines surface active exceptions in PR summaries to ensure temporary
   allowances receive scrutiny.

## Integration with CLI Outputs

- CLI commands emit SHA256 hashes and JSONL streams; quality bots record these to
  prove that benchmark inputs/outputs were unchanged.
- When running `geosync-cli backtest --output jsonl`, the pipeline pipes the
  results through `jq` scripts that calculate regression deltas and post them to
  the run summary.

## Reporting

- Weekly reports aggregate gate outcomes, open exceptions, and regression trends
  into the Quality dashboard.
- Error budget consumption from `docs/reliability.md` is overlaid with gate
  statuses so leadership can prioritise fixes versus feature work.

## Break-Glass Workflow

- **Triggering** – When a production rollback or hotfix must bypass gates,
  engineers raise an emergency ticket and open a "break-glass" PR tagged with
  `needs-postmortem` that documents the justification and temporary scope.
- **Execution** – The PR follows the reduced checklist stored in
  [`reports/prod_cutover_readiness_checklist.md`](../reports/prod_cutover_readiness_checklist.md)
  to capture validation evidence even while bypassing normal automation.
- **Post-mortem** – Within 48 hours, the owning team files a retrospective and
  links it from the relevant runbook (for example
  [`docs/runbook_data_incident.md`](runbook_data_incident.md)). Follow-up actions
  enter the governance backlog described in [`docs/governance.md`](governance.md).

Quality gates shift enforcement left: developers receive immediate feedback in
PRs, nightly automation provides early detection, and governance artifacts keep
stakeholders aligned.
