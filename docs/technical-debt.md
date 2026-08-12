# Technical Debt Management Playbook

Effective technical debt management keeps GeoSync teams nimble without
sacrificing platform stability. This playbook formalises how we identify,
prioritise, and retire debt across services, data pipelines, and research
artifacts.

> **Live registry:** See `reports/TECH_DEBT_REGISTRY.md` for the current, prioritised debt ledger with owners and closure criteria.

## Guiding Principles

- **Visibility first.** Debt must be explicitly logged, tagged, and visible in
the same tooling used for feature work so prioritisation conversations are
grounded in data.
- **Flow over utilisation.** Lean limits on simultaneous debt efforts protect
focus and keep risky refactors from stalling delivery pipelines.
- **Continuous paydown.** A predictable slice of every sprint prevents large,
urgent debt crises from erupting during critical release windows.

## Dedicated Backlog Structure

1. **Separate board / swimlane.** All debt items (code, infrastructure,
   documentation, and research models) live in a dedicated backlog column or
   swimlane that mirrors the product backlog workflow (Ready → In Progress →
   Review → Done).
2. **Debt taxonomy.** Label tickets using a consistent taxonomy so that teams
   can filter by risk and domain:
   - `debt/refactor` – structure or readability issues.
   - `debt/perf` – performance or scalability gaps.
   - `debt/tooling` – automation, CI/CD, observability gaps.
   - `debt/docs` – missing or outdated documentation/tests.
3. **Sizing and acceptance.** Apply the same estimation units as feature work
   (story points or flow metrics) and require clear acceptance criteria that
   describe the new desired state and validation method.
4. **Quarterly review.** Once per quarter the architecture group audits the
   backlog, closes stale tickets, and revalidates priority, ensuring that
   debt items align with current roadmaps and incident learnings.

## WIP Limits for Debt Paydown

- **Squad-level limit.** Each squad may have at most `⌈N / 3⌉` concurrent debt
  stories in progress, where `N` is the number of engineers available in the
  sprint (rounded up). This ensures debt work never exceeds one focused pair or
  mob at a time in smaller teams.
- **System guardrails.** Configure the project management tool to block pulling
  new debt items when the limit is reached; require a retro action if a team
  overrides the limit.
- **Exception handling.** Exceed the limit only for Sev-1 security or
  compliance remediations and document the override in the sprint report.
- **Flow metrics.** Track lead time and throughput for debt stories separately
  to confirm that WIP limits are improving cycle time instead of causing hidden
  queues.

## Sprint Capacity Allocation

1. **Baseline allocation.** Reserve **20% of each sprint capacity** for debt
   retirement (e.g., 10 points in a 50-point sprint). Treat this as a budget
   that must be deliberately spent; unused capacity rolls into the next sprint
   only if the backlog truly has no ready debt tickets.
2. **Dynamic adjustments.** Use the following triggers to adjust the baseline:
   - Increase to **30–35%** when mean time to recovery (MTTR) or defect escape
     rate worsens for two consecutive sprints.
   - Decrease to **10–15%** only when operational metrics are green and the
     roadmap carries immovable deadlines approved by product and engineering
     leadership.
3. **Pairing with features.** When possible, bundle debt cleanup with adjacent
   feature work, but log the cleanup as a distinct ticket so the allocation is
   still tracked and reported.
4. **Sprint review checkpoint.** Demonstrate completed debt stories alongside
   features, highlighting the risk reduced and the validation evidence.

## Operational Cadence

1. **Intake.** Engineers raise debt tickets as part of code reviews, incident
   post-mortems, or discovery spikes. Tickets include the root cause,
   containment status, proposed remediation, and validation plan.
2. **Prioritisation.** During backlog refinement, rank debt items by
   engineering risk, customer impact, and proximity to upcoming roadmap work.
   The tech lead ensures at least one high-risk debt item is always pulled into
   the next sprint.
3. **Execution.** Debt stories follow the same definition of done as feature
   work: code merged, tests updated, documentation refreshed, and monitoring
   adjusted.
4. **Reporting.** Include a dedicated slide in sprint reviews summarising debt
   throughput, WIP, allocation usage, and key wins. Publish quarterly metrics to
   the engineering wiki for transparency.

## Metrics and Tooling Checklist

| Metric | Why it matters | Target | Source |
| ------ | -------------- | ------ | ------ |
| Debt WIP | Ensures WIP limits are respected | `≤ ⌈N / 3⌉` stories | Project board |
| Debt Throughput | Validates steady paydown | ≥ 1 completed story / sprint | Jira/Linear reports |
| Allocation Burn | Confirms sprint % was utilised | 90–110% of planned capacity | Sprint report |
| Aged Debt | Flags tickets older than 90 days | < 10% of backlog | Saved filter |
| Defect Escape Rate | Measures impact of debt | Downward trend quarter over quarter | QA dashboard |
| MTTR | Signals operational risk | < 4 hours | Incident management tool |

Automate weekly exports of these metrics into the analytics workspace; surface
trends on the engineering operations dashboard so deviations trigger alerts.

## Roles and Responsibilities

- **Engineering Managers:** Enforce allocation budgets, facilitate prioritisation
  trade-offs, and escalate systemic blockers.
- **Tech Leads:** Curate the debt backlog, validate sizing, and ensure remedial
  work is technically sound.
- **Engineers:** Raise debt tickets proactively and pair on complex remediation
  items to share knowledge.
- **Product Managers:** Coordinate roadmap adjustments when debt threatens key
  outcomes and communicate customer impact of deferred fixes.
- **Architecture Council:** Review quarterly health metrics, approve structural
  refactors, and align debt remediation with long-term platform vision.

## Example Sprint Allocation Plan

| Sprint Capacity (points) | 20% Debt Budget | Typical Breakdown |
| ------------------------ | --------------- | ----------------- |
| 40 | 8 | 1 refactor (5 pts), 1 observability task (3 pts) |
| 50 | 10 | 1 infrastructure hardening (6 pts), 1 doc/test update (4 pts) |
| 60 | 12 | 1 performance tuning (8 pts), 1 migration follow-up (4 pts) |

## Continuous Improvement

- Conduct a semi-annual retrospective dedicated to debt management outcomes.
- Refresh WIP limits if team size or flow efficiency shifts significantly.
- Track qualitative wins (e.g., faster onboarding, reduced incidents) alongside
  quantitative metrics to maintain stakeholder support.

By institutionalising these practices we keep innovation velocity high while
ensuring the GeoSync platform remains reliable, observable, and compliant.

## External CI Repair Intake Gate

External run repair is a distinct tooling debt class: an agent can receive a
GitHub Actions run from another repository while the mounted workspace points at
a different checkout. That state must be detected before code changes, because a
patch in the wrong repository creates false evidence and cannot repair the red
CI blocks.

Use this deterministic intake before external-run work; the target may be an
`owner/repository` slug, a repository URL, or a GitHub Actions run URL:

```bash
python scripts/ci/external_run_intake.py --target-repo neuron7xLab/bive
python scripts/ci/external_run_intake.py --target-repo https://github.com/neuron7xLab/bive/actions/runs/27351344416
```

The gate reads local repository identity from `pyproject.toml`, branch state from
`git branch --show-current`, git SHA/dirty state from local git commands, and
configured remotes from `git remote -v`. It does not fetch network resources.
`PASS` means the mounted workspace identity is parseable, the worktree is clean,
and an exact `owner/repository` remote on an allowed Git host matches the
requested repository. `FAIL` means repair is blocked and the emitted JSON lists
exact blockers, for example `INVALID_TARGET_REPO`, `UNTRUSTED_TARGET_HOST`,
`UNREADABLE_PYPROJECT`, `REPOSITORY_IDENTITY_MISMATCH`, `DIRTY_WORKTREE`,
`MISSING_GIT_REMOTE`, or `TARGET_REMOTE_NOT_CONFIGURED`.

Acceptance invariant: external CI repair may not patch files until this intake
returns `repair_allowed: true` for the target repository. UNKNOWN or missing
network state remains outside this gate and must be recorded separately in the
release evidence bundle. Dirty worktrees are blocked by default; `--allow-dirty`
may be used only for read-only audits where the dirty state is still recorded in
the JSON payload.
