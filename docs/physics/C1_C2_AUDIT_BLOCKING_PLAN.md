# C1 C2 Audit Blocking Plan

Date: 2026-05-29

## Goal

Move the physics code audit from informational mode to blocking mode only after the audit count reaches zero.

## Current blocker

The workflow command still permits audit failure with `|| true`. This is intentional while the backlog is unknown.

## Safe transition

1. Run the code audit locally.
2. Record the exact issue count in the P0 closure ledger.
3. Fix or annotate every reported clamp or numeric bound.
4. Re-run the audit until the issue count is zero.
5. Remove `|| true` from the workflow.
6. Add the workflow update as the final commit in the closure batch.

## Non-goal

Do not flip the workflow to blocking before the count is zero. A red gate with known backlog is noise, not safety.
