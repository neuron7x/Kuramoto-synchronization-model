# Operations Guide: Thermodynamic Validation and Progressive Rollout

This runbook explains how to triage failures in the thermodynamic validation
(`validate-energy`) and Progressive Release Gates workflows.

## Reading `validate-energy` Failures

1. Download the artifacts from `.ci_artifacts/energy_validation.json`.
2. Inspect `free_energy`, `internal_energy`, and `entropy`.
   - If `free_energy` > 1.35 the validator rejected the build.
   - Review `penalties` to determine which metric exceeded its normalised limit.
3. Cross-reference the metric with production dashboards for corroborating data.
4. File an incident if the degradation also appears in production telemetry.

## Restoring Service Without Downtime

- Deploy the latest healthy build to the **Blue** slice while the **Green**
  slice continues to serve traffic.
- Apply the remedial patch to the Blue slice and monitor the energy metrics for
  two consecutive five-minute windows.
- When the free energy stays below 1.35 and no release gate fails, promote Blue
  to primary and keep Green on standby.

## Approving Changes That Increase `F`

1. Capture the post-change telemetry snapshot and attach
   `.ci_artifacts/energy_validation.json` to the release ticket.
2. Obtain approval from both the Thermodynamic Duty Officer and the responsible
   Platform Staff Engineer (see `docs/TACL.md`).
3. Record the justification in `release-notes.md` under the "Thermodynamic
   Changes" section to maintain the audit trail.

## Manual Rollout Confirmation

When automated rollback triggers, the controller writes `e2e_rollout_summary.json`
with the failing gate reasons.  To manually confirm the fix:

1. Re-run `python -m tacl.validate --run smoke` against the patched build.
2. Execute `python -m tacl.release_gates --config ci/release_gates.yml` and check
   that all gates report `"passed": true`.
3. Launch the Blue/Green stage manually if required by executing the GitHub
   Actions workflows:
   - `thermodynamic-validation.yml`
   - `progressive-release-gates.yml`
   - `progressive-rollout-blue-green.yml` (if a custom workflow exists)
4. Verify the canary ramp-up in the deployment dashboard and ensure the audit
   log contains the automatic rollback entry for regression tests.
