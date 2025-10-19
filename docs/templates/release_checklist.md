---
owner: release@tradepulse
review_cadence: per-release
last_reviewed: 2025-02-14
links:
  - docs/runbook_release_validation.md
  - docs/documentation_standardisation_playbook.md
---

# Release Checklist: <Version/Train>

<details>
<summary>How to use this template</summary>

- Copy this template into `reports/` or `docs/` depending on visibility.
- Align checklist items with Quality Gates, DoR/DoD, and release readiness
  reviews.
- Convert checkboxes to `[x]` as tasks complete; archive results post-release.
- Remove this block when finalising the checklist.

</details>

## Summary

- **Release Owner:**
- **Cutover Window:**
- **Rollback Owner:**
- **Related ADRs / RFCs:**

## Pre-Release Validation

- [ ] All required ADRs merged and referenced in release notes.
- [ ] Test suite (unit/integration/e2e) passes in CI.
- [ ] Security scans (CodeQL, Semgrep, Bandit, Safety) green.
- [ ] Documentation updates merged (READMEs, API contracts, runbooks).
- [ ] Feature toggles documented with enablement criteria.

## Deployment Plan

| Step | Owner | Command / Link | Verification |
| ---- | ----- | -------------- | ------------ |
| 1 | | | |

## Post-Deployment Verification

- [ ] SLO dashboards show baseline error budgets.
- [ ] Canary metrics within tolerances.
- [ ] Incident response roster acknowledged.
- [ ] Release notes published to changelog and status page.

## Contingency

- [ ] Rollback script validated in staging.
- [ ] Data migrations reversible or backup verified.
- [ ] Communication plan for rollback prepared.

## Sign-off

| Role | Name | Date | Notes |
| ---- | ---- | ---- | ----- |
| Release Manager | | | |
| Domain Owner | | | |
| SRE | | | |

## Retrospective

- **Highlights:**
- **Improvements:**
- **Action Items:**
