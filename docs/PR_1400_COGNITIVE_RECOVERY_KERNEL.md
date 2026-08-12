# PR #1400 Cognitive Recovery Kernel

Status: active operator handoff artifact  
Scope: `second-order-energy-stream-clean`  
Audience: Claude Code / Codex / GitHub-connected recovery agents  
Verdict vocabulary: `ACCEPT`, `REVISE`, `BLOCK`, `CLOSE`

## 0. Purpose

This document encodes the latent intent behind PR #1400 as an executable
engineering kernel. It is not a motivational note, a claim expansion, or a
marketing layer. It is a recovery contract for future agents that must continue
this PR without diluting its falsification standard.

The human operator's signal is stronger than the explicit wording: the requested
outcome is not merely to make CI green. The outcome is to leave behind an
artifact that makes the next recovery step harder to misunderstand, harder to
fake, and harder to silently weaken.

The kernel is therefore:

```text
intent -> invariant -> falsifier -> minimal patch -> evidence -> verdict
```

If a future agent cannot map an action to that chain, the action is out of
scope.

## 1. Prime directive

Do not optimize for apparent success. Optimize for verified closure.

A green check is acceptable only when it is produced by the real gate, on the
current PR head, without lowering floors, hiding tests, weakening physics claims,
expanding scientific assertions, or creating a green-by-vacuum condition.

Every patch must preserve the original PR law:

```text
streamed swing-energy audit
same formula
O(N^2) peak pairwise memory
no dense T*N*N trajectory tensor
no claim expansion
no mutation-floor reduction
```

## 2. Latent semantic expansion rule

When the operator gives an underspecified command, infer the missing engineering
content from repository state, not from confidence theater.

Use this decoder:

```text
"make it green"
  means: isolate the exact failing gate and remove the root cause without hiding
  the tested surface.

"solid artifact"
  means: leave a repository-local document, test, guard, or diagnostic that makes
  the recovered invariant reusable by future agents.

"extrapolate"
  means: infer the next required falsifier from the existing evidence graph, then
  execute the smallest patch that makes that falsifier pass honestly.

"do not give me trash"
  means: no cosmetic commits, no broad rewrites, no speculative architecture, no
  partial bypass, no narrative-only closure.
```

The agent must compute what was not fully said by reading the structure of the
failure: changed files, gate logs, existing acceptor scope, invariant documents,
mutation floors, PR body, and branch protection semantics.

## 3. Current recovery frontier

At the time this kernel was created, the PR had already passed the independent
physics, mutation, hygiene, readiness, import, architecture, repo-integrity,
feature-debt, and security gates on the current recovery head. The remaining
systemic blocker was the PR Gate fast lane, specifically the sharded fast pytest
surface.

Important interpretation:

- A red fast shard is not automatically a product-code regression.
- Four red fast shards suggest a fast-lane orchestration issue or timeout unless
  logs prove otherwise.
- A test-surface PR must never pass with zero collected tests.
- Quarantine is allowed only for tracked, deterministic backlog already recorded
  with an issue reference and expiry condition.
- Increasing deterministic shard count is allowed when it reduces timeout risk
  while preserving the same selected node-id universe.

Preferred next recovery vector if logs remain non-diagnostic:

```text
python-fast-shard: 4 deterministic crc32 buckets -> 8 deterministic crc32 buckets
```

This is not a test reduction. It is the same test universe split into smaller
serial shards. The invariant is unchanged:

```text
all collected non-quarantined fast node ids must be run by exactly one shard
```

## 4. Claude Code execution contract

A future Claude Code agent must follow this sequence:

```text
1. Read PR state, current head SHA, changed files, and latest workflow runs.
2. Confirm whether PR Gate is still the only failing workflow.
3. If a job failed, inspect its logs or emitted artifacts before patching.
4. If logs show test failures, patch only the failing production/test contract.
5. If logs show timeout or non-diagnostic shard collapse, patch orchestration only.
6. Keep commit acceptor diff_scope synchronized with every new or changed file.
7. Re-run the smallest sufficient gate set.
8. Report only evidence-backed status: ACCEPT / REVISE / BLOCK / CLOSE.
```

Forbidden behaviors:

```text
- Do not lower mutation floors.
- Do not weaken physics invariants.
- Do not delete tests to make CI green.
- Do not broaden the scientific claim.
- Do not reintroduce dense T*N*N energy allocation.
- Do not mark success while any required workflow is pending or red.
- Do not add a new file without binding it to the commit acceptor scope.
- Do not treat lack of visible log output as proof of success.
```

## 5. Minimal acceptable PR Gate patch pattern

If the failure remains four red fast shards with no specific FAILED/ERROR node
ids, prefer this patch shape:

```yaml
strategy:
  fail-fast: false
  matrix:
    group: [1, 2, 3, 4, 5, 6, 7, 8]
```

and update the shard partition from `% 4` to `% 8` wherever the matrix cardinality
is encoded. The implementation should avoid duplicated magic numbers where
possible, for example by deriving the shard count from a matrix environment
value.

The expected evidence after such a patch:

```text
- repo-policy passes pinned-action and PR-gate-contract checks;
- python-quality remains green;
- every python-fast-shard bucket completes;
- python-fast-tests aggregator passes only after all shards pass;
- heavy/security/dependency gates remain unchanged;
- no workflow passes by skipping a relevant test surface.
```

## 6. Artifact inheritance law

This file is a continuation anchor. It exists so future agents do not merely
inherit code; they inherit the epistemic posture of the recovery.

The posture is:

```text
The human is the falsifier.
The LLM expands candidate state space.
GitHub materializes state.
CI executes adversarial measurement.
The verdict is earned only by evidence.
```

The agent must not imitate certainty. It must produce it by shrinking the gap
between claim and falsifier.

## 7. Final acceptance theorem

PR #1400 is merge-ready only when this predicate is true on the latest PR head:

```text
mergeable == true
and draft == false only by explicit human intent
and all required checks == success
and mutation floor unchanged
and commit acceptor scope matches diff
and streamed energy invariant preserved
and PR Gate fast lane is real-green, not green-by-vacuum
```

Until then, the only valid verdict is:

```text
REVISE or BLOCK
```

When the predicate is true, the only valid final verdict is:

```text
ACCEPT — human merge approval still required
```
