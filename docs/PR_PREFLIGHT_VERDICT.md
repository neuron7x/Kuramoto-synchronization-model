# PR Preflight Verdict Contract

## Purpose

The PR preflight verdict is the human-readable summary produced from two machine-readable artifacts:

- `artifacts/pr_preflight/preflight_report.json`
- `artifacts/pr_preflight/inference_ledger.jsonl`

The report describes the current run. The ledger preserves the sequence of runs. The verdict must not replace either artifact. It is an interface for reviewers.

## Inputs

A valid verdict generator must read:

1. the latest preflight report;
2. the latest ledger entry when the ledger exists;
3. the critical check list;
4. blocked, failed, timeout and skipped-optional check identifiers;
5. the first file to open.

## Output

The generated verdict must be Markdown and must include:

- final status: `PASS`, `FAIL` or `BLOCKED`;
- failure count;
- critical failed checks;
- blocked checks;
- timeout checks;
- skipped optional checks;
- next deterministic action;
- evidence file paths.

## Fail-Closed Rules

The verdict generator must fail instead of producing a misleading summary when:

- the report is missing;
- the report schema is invalid;
- the final status is unknown;
- a critical check is marked skipped optional;
- `failure_count` contradicts critical check evidence;
- the ledger exists but the latest entry contradicts the report.

## Non-Goals

The verdict is not a CI pass substitute. It is not a production-ready claim. It is not a replacement for tests. It is a compact review interface over evidence that already exists.

## Product Boundary

The local PR preflight product is complete only when this chain is present:

```text
command -> report JSON -> ledger JSONL -> verdict Markdown -> CI gate -> merge decision
```

Any missing link is a blocker for claiming a complete local preflight evidence system.
