# PR #1416 External Agent Onboarding

Repository: `neuron7xLab/GeoSync`

PR: `#1416`

Branch: `agent-dopamine-v2`

Purpose: move an external repair agent from zero context to autonomous, evidence-gated operation.

## Operating invariant

The agent must preserve this chain:

`law -> witness -> artifact -> readiness -> test -> shard -> CI -> merge`

The agent may only report merge readiness when every required check for the current PR head is terminal green.

## Required starting context

Read these files first:

- `docs/ci/pr-1416-fail-closed-repair-protocol.md`
- `docs/ci/pr-1416-agent-onboarding.md`
- `.github/workflows/research-integrity-gate.yml`
- `.github/workflows/pr-gate.yml`
- `.claude/commit_acceptors/pr-1416-repair-protocol.yaml`
- `.claude/commit_acceptors/research-pandas-datetime-guard.yaml`
- `.claude/commit_acceptors/instrument-evidence-reconciliation.yaml`

## Autonomous loop

1. Lock the current PR head and merge ref.
2. Enumerate all required checks for that head.
3. Select the first terminal red required check.
4. Identify the exact failed job and step.
5. Fetch the exact log or artifact for that step.
6. Extract the precise failing node, blocker, or assertion payload.
7. Classify the root cause before editing code.
8. Patch only the causal file set.
9. Preserve or add a regression test for the defect.
10. Ensure all changed paths are commit-acceptor bound.
11. Push and wait for Commit Acceptor Gate.
12. Re-check the original red gate.
13. Repeat until all required checks are terminal green.

## Research Integrity decision tree

If `pytest — research/systemic_risk` fails, use `research-systemic-risk-pytest-log` and patch only the systemic-risk causal defect.

If `Instrument evidence-chain reconciliation gate` fails, use `instrument-evidence-chain-log` and classify the failure as source drift, missing file, acceptor binding, collect oracle, or provenance.

If `pytest — evidence-truth gates + research-line contracts` fails, use `evidence-truth-pytest-log` and patch the exact failing pytest node only.

If mypy, ruff, or black fails, patch the type/style issue only.

## PR Gate decision tree

If `python-quality` fails, patch lint, format, or type issues only.

If a `python-fast-shard` fails, extract the exact failed node. If logs are truncated, add artifact capture to the existing PR Gate only.

If security or dependency review fails, fix the real finding or the baseline path mismatch. Do not suppress without a recorded reason.

If repo-policy fails, fix the policy or acceptor binding. Do not bypass the policy.

## Transition logging

Every transition must be recorded with these fields:

- event id
- UTC time
- PR head SHA
- merge SHA
- trigger
- observed state
- decision
- action
- changed paths
- evidence
- next check
- merge status

Rules:

- append new events only
- never overwrite prior events
- do not guess missing data
- if Commit Acceptor fails, pause downstream conclusions until binding is fixed

Current state snapshot:

- head: `63aa75a4a1804909121a9ac0df18765a98048ba0`
- merge: `9436575b6399d95c55b116ef5a013bafb2062266`
- Commit Acceptor Gate: success
- Research Integrity Gate: in progress
- PR Gate: in progress
- Repo Integrity Gate: in progress
- merge status: blocked until all required checks are terminal green

## Non-negotiable prohibitions

- no deleted tests
- no hidden skip
- no xfail without issue and expiry
- no relaxed assertion
- no severity downgrade without ledger reason
- no fake quarantine
- no unbound diagnostic workflow
- no merge while any required check is red or pending

## Final report format

VERDICT: PASS / FAIL / IN PROGRESS

Tested head: `<sha>`

Current blocker: `<workflow / job / step / none>`

Root cause: `<one exact sentence>`

Patch: `<changed paths>`

Evidence:

- Commit Acceptor Gate: PASS / FAIL
- Research Integrity Gate: PASS / FAIL
- PR Gate: PASS / FAIL
- relevant artifact or log: `<name / none>`

No weakening: yes / no
