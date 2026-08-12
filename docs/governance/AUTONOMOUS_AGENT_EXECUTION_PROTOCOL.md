<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Autonomous Agent Execution Protocol

> **Governance contract for research-engineering agents operating on GeoSync.**
> This is a contract, not advice. Every clause is normative (`MUST` / `MUST NOT`)
> and machine-checkable against
> [`AUTONOMOUS_AGENT_EXECUTION_PROTOCOL.contract.json`](AUTONOMOUS_AGENT_EXECUTION_PROTOCOL.contract.json).

This protocol governs any agent — Claude, Codex, or other automation — that
executes work against this repository. It is subordinate to and consistent with
the existing governance surface:
[`PRODUCT_CATEGORY.md`](../../PRODUCT_CATEGORY.md),
[`CLAIMS.md`](../../CLAIMS.md),
[`FORBIDDEN_CLAIMS.md`](../../FORBIDDEN_CLAIMS.md),
[`AGENTS.md`](../../AGENTS.md), and
[`docs/REPOSITORY_SYSTEM.md`](../REPOSITORY_SYSTEM.md). Where this document and an
authority file appear to disagree, the authority file wins and this document is
the drift that must be repaired.

GeoSync is a verification-first research platform. Its product-category boundary
is declared canonically in [`PRODUCT_CATEGORY.md`](../../PRODUCT_CATEGORY.md), and
nothing in this protocol authorizes an agent to widen that boundary.

---

## 1. Role

An agent operating under this protocol is an **autonomous execution unit**. It is
explicitly an autonomous execution unit and not a report-only assistant.

```text
MUST  carry work to a terminal, verifiable state (merged-by-owner, or an
      explicitly recorded BLOCKED state) rather than stopping at a description
      of what could be done.
MUST  produce replayable artifacts and deterministic commands, not prose
      confidence.
MUST NOT  treat "I have explained the change" as completion. An explanation is
          not an execution.
```

A report that is not bound to an executed, falsifiable artifact is repository
mass, not work delivered.

---

## 2. Delegated Execution Authority

The agent holds delegated authority to act on the local checkout and on GitHub
within bounded limits.

```text
MUST  be allowed to create branches.
MUST  be allowed to create commits on a non-default branch.
MUST  be allowed to open pull requests, push to its own feature branch, and
      drive CI to a green state.
MUST  be allowed to run local gates, tests, and verification commands.
```

This authority is **delegated and bounded**. It exists to remove human
round-trips on mechanical execution, not to remove human judgment on promotion.

---

## 3. Authority Boundary (MUST NOT)

The following are hard limits. A run that crosses any of them is a protocol
violation regardless of test color.

```text
MUST NOT  push directly to main / master (the default branch).
MUST NOT  merge a pull request. Merge authority is owner-only.
MUST NOT  rewrite, recompute, or overwrite frozen artifacts (byte-frozen
          RESULTS.json, frozen calibration replays, locked evidence bundles,
          MANIFEST.sha256 entries that pin a prior result).
MUST NOT  weaken a threshold, tolerance, falsifier bound, schema constraint, or
          gate to make a failing artifact pass.
MUST NOT  delete a failed, blocked, retired, or negative result that carries
          evidence value.
MUST NOT  promote a claim tier by wording alone, bypassing CLAIMS.md.
```

Owner-only merge is the keystone: the agent prepares evidence; a human owner
decides promotion.

---

## 4. Red Pull Request Stays Blocked

A pull request whose CI is red, pending, or unverifiable is not a candidate for
merge and the agent must not present it as one.

```text
MUST  keep a red or pending PR in draft / blocked state.
MUST  either diagnose and fix a CI failure locally and re-push, or record an
      explicit BLOCKED state with a 7-field evidence note.
MUST NOT  mark a PR ready-for-review while any required check is failing or
          pending.
MUST NOT  leave a PR in a silently failed-CI state.
```

---

## 5. Green Is Not Enough — Perturbation Is Mandatory

A green test suite proves that the code did not break under the inputs the suite
happened to choose. It does not prove the result is robust. Before an agent
presents any result-bearing change as ready, it **MUST shake the result** along
the perturbation axes below and record the outcome.

```text
MUST  perturb seed        — re-run under a different deterministic seed; a result
                            that only holds at one seed is not a result.
MUST  perturb horizon     — vary the forecast / evaluation horizon.
MUST  perturb window      — vary the rolling / lookback window length.
MUST  perturb scale       — vary input magnitude / units / normalization.
MUST  inject missing data — drop rows / introduce gaps and confirm fail-closed
                            behavior, not silent imputation.
MUST  inject malformed metadata — corrupt or omit metadata and confirm the
                            pipeline rejects rather than guesses.
MUST  test null / baseline bypass — confirm the null or baseline path cannot be
                            skipped to manufacture a passing comparison.
MUST  test cost NOT_RUN   — confirm a not-run cost model surfaces as
                            BLOCKED_COST_MODEL, never as a silent pass.
MUST  test replay mismatch — confirm a replay that does not reproduce the
                            recorded hash fails closed, never auto-heals.
```

A perturbation that the change is genuinely exempt from (for example, a
documentation-only change has no seed or horizon) **MUST** be recorded as
`N/A — <reason>`, not silently omitted. Silence is indistinguishable from a
skipped check.

```text
MUST NOT  present a result as ready on green tests alone.
MUST NOT  record a perturbation axis as passed without running it.
```

---

## 6. Required Pull Request Disclosure

Every pull request opened under this protocol **MUST** include the following
sections. A PR missing any required field is incomplete and **MUST NOT** be
marked ready.

```text
MUST  scope                  — what the change is and the exact subsystem touched.
MUST  claim boundary         — what is and is NOT being claimed; tier impact.
MUST  changed files          — exhaustive list, grouped by surface/role.
MUST  commands               — the deterministic commands that were run.
MUST  results                — outcomes, exit codes, evidence pointers.
MUST  stress checks          — the Section 5 perturbation matrix and its results.
MUST  evidence artifacts     — paths to replayable artifacts (or N/A + reason).
MUST  frozen-artifact status — confirmation that no frozen artifact was rewritten.
MUST  limitations            — honest list of what this does not establish.
MUST  next failure surface   — where this is most likely to break next.
```

These fields map onto the evidence-bearing artifact minimum in
[`AGENTS.md`](../../AGENTS.md) and the reviewer protocol in
[`docs/REPOSITORY_SYSTEM.md`](../REPOSITORY_SYSTEM.md); this protocol does not
relax either.

---

## 7. Stop Condition

If any gate can only be made to pass by faking, weakening, deleting evidence, or
rewriting a frozen artifact, the agent **MUST STOP** and record a blocked result
instead of forcing a green state.

```text
MUST  return a BLOCKED result rather than weaken a gate.
MUST  record the blocker as a 7-field evidence note (what was attempted, the
      exact gate, the observed failure, why it cannot pass honestly, the frozen
      / threshold surface involved, the safe next step, and the owner decision
      required).
MUST NOT  invent context, fabricate evidence, or downgrade a falsifier to escape
          a stop condition.
```

Incomplete proof stops at the boundary. It does not promote.

---

## 8. Relationship to the Governance Surface

```text
- PRODUCT_CATEGORY.md  — product-category boundary; this protocol never widens it.
- CLAIMS.md            — claim-tier ledger; the sole promotion path.
- FORBIDDEN_CLAIMS.md  — status-language firewall; this protocol inherits it.
- AGENTS.md            — implementation-agent contract; the artifact minimum and
                         inference operation protocol still apply.
- REPOSITORY_SYSTEM.md — system map, reviewer protocol, completion definition.
```

This document adds the **execution-authority and perturbation** layer on top of
those surfaces. It does not replace any of them.
