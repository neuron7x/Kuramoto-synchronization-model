# Coverage Ascent Work Act 92-97

Status: engineering protocol, not a readiness claim.

## 1. First principles

Coverage is not the goal. Coverage is an instrument for exposing unobserved production behavior. A test is valuable only when it can kill a wrong implementation, detect an unsafe state, or falsify a claim. The campaign therefore optimizes truth-density, not test count.

The repository-tracked baseline is 85.03 percent release-line coverage, below the 90 percent release gate. The first target surface is `backtest`, because it has the largest measured deficit: 68.55 / 98. The next surfaces are `risk`, `execution`, `core`, `ingestion`, and `analytics`.

No threshold may be lowered. No omit rule may be expanded. No module may be skipped to inflate a number. Any claim of 90, 92, 95, or 97 percent requires same-commit machine evidence from the release coverage authority.

## 2. Value function

Each new test must maximize at least one of these values:

- falsification power: it fails for a plausible wrong implementation;
- risk reduction: it protects money, state, data, orders, or scientific claims;
- invariant capture: it pins a law that should hold across many inputs;
- boundary defense: it covers empty, non-finite, stale, duplicated, malformed, or adversarial inputs;
- regression locality: when it fails, the broken responsibility is obvious;
- deterministic replay: it gives the same verdict across machines and time;
- evidence integrity: it improves the measured release surface without hiding code.

A shallow test that only executes a line but cannot distinguish correct from wrong behavior has low value even if it raises coverage.

## 3. Methodology

The campaign proceeds by surface-risk ordering, not by convenience. First raise `backtest`, then harden `risk` and `execution`, then lift `core`, then `ingestion`, then `analytics`.

For every targeted file, derive tests from contracts:

1. identify the production responsibility;
2. list invariants and failure modes;
3. write the smallest deterministic fixtures;
4. assert behavioral properties, not implementation trivia;
5. include negative paths and edge states;
6. run the local test slice;
7. run full release coverage;
8. record exact evidence artifacts.

## 4. Required protocols

Backtest protocol: cover split-boundary determinism, no look-ahead leakage, empty input, non-finite input, duplicate and unsorted timestamps, signal/price length mismatch, fee and slippage monotonicity, equity accounting, constant-price cases, and single-row cases.

Risk and execution protocol: cover invalid order rejection, duplicate order identity, stale transitions, idempotent ledger updates, explicit compliance rejection, gross exposure accounting, position-sizing monotonicity, circuit-breaker states, stale quotes, deterministic arbitrage ranking, and fee-aware profitability.

Core protocol: cover model validation, deterministic serialization, invalid configuration rejection, normalization boundaries, mathematical invariants, safe error redaction, and local fixtures only.

Analytics and market protocol: cover empty-tree handling, malformed-file handling, deterministic aggregation, invalid adapter configuration, order-book bid/ask invariants, crossed-book rejection, idempotent depth updates, sequence-gap detection, and stale event rejection.

## 5. Quality requirements

Every coverage PR must be test-only unless a test exposes a real bug; bug fixes must be split or explicitly justified. Tests must be deterministic, offline, small, readable, and tied to a production responsibility. Tests must include at least one failure-mode assertion when the module has reject paths. Tests must not depend on external services, live data, wall-clock randomness, or broad monkeypatching that bypasses the unit under test.

## 6. Maturity gates

A weak test only imports, snapshots output, asserts type shape, or exercises a happy path. A strong test protects an invariant, rejects a bad state, checks a boundary, or proves monotonic behavior. An elite test fails when a small mutation of the production logic violates the real contract.

## 7. Cognitive test economics

Prefer tests with high defect-yield per line: one compact fixture should exercise several meaningful states without becoming opaque. Prefer property-style invariants over brittle literal outputs when the contract is mathematical. Prefer table-driven cases when the module has many boundary states. Prefer explicit negative cases over passive execution. Prefer local deterministic data over external datasets.

## 8. Anti-patterns

Reject tests that only import a module, only assert that a function returns something, only pin incidental formatting, only monkeypatch the decision logic, or only duplicate the implementation in the assertion. Reject coverage gains created by hiding files, lowering targets, adding broad skips, or moving code outside the release surface.

## 9. Excellence bar

A test suite is solid only when it can explain what production promise it protects. It must make future refactors safer, not harder. It must reduce ambiguity for a human reviewer and for an automated agent. It must produce evidence that is reproducible, local, and tied to the canonical release surface.

## 10. Definition of done

A PR is done only when new tests pass, the full release coverage measurement completes, the coverage intelligence report is valid, the release-line number moves or the zero movement is explained, and the PR body names the exact targeted files and behaviors. Evidence must include coverage summary, gap map, next-tests report, and the test command used.

## 11. Review contract

Reject coverage PRs that raise the percentage by hiding source, weakening thresholds, broad-skipping dependencies, snapshotting incidental output, or testing mocks instead of production behavior. Approve only when the new test would fail for at least one realistic bad implementation.

## 12. Evidence checklist

Each follow-up coverage PR must state targeted files, targeted behaviors, old release-line value, new release-line value, surface movement, exact command, and artifact paths.

## 13. Immediate next unit

Open a test-only PR for `backtest/walk_forward.py` and `backtest/geosync_equity_curve.py`. The goal is not cosmetic coverage. The goal is to convert backtest replay logic into a falsifiable, deterministic, failure-resistant surface on the path from 85.03 percent to 92-97 percent.
