# WP-01 — PR Collision Governance Protocol

**Research question.** How do we stop two open PRs from closing the *same* claim?

**Failure mode.** Two open, non-draft PRs edit the same single-source-of-truth
governance file (or reference the same Task/P0/WP lane). If both merge, `main`
gets two competing definitions of one gate — governance schizophrenia. This is
exactly what #1120 / #1121 (both "Task 2 dependency all-strict", both editing
`tools/security/check_dependency_manifest_consistency.py`) would have produced.

## Detection

[`tools/governance/check_pr_lane_collision.py`](../../tools/governance/check_pr_lane_collision.py)
flags a collision between two open non-draft PRs when **either**:

1. they share a changed file matching a **critical source-of-truth glob**
   (`tools/security/*.py`, `tools/governance/*.py`, `tools/claims/*.py`,
   `tools/release/*.py`, `governance/*.yaml`, `schemas/**`, `requirements*.txt`,
   `constraints/*.txt`, `pyproject.toml`, `.claude/physics/INVARIANTS.yaml`); **or**
2. they share a normalized lane token (`task N`, `p0-N`, `wp-NN`) **and** overlap
   on any changed file.

A shared lane token *alone* (no file overlap) is not a collision — different
work may reference one task. A shared non-critical file alone (no lane token) is
not a collision either. Both guards exist to avoid false positives.

## Running

```bash
python tools/governance/check_pr_lane_collision.py            # live scan via gh
python tools/governance/check_pr_lane_collision.py --json     # machine output
python tools/governance/check_pr_lane_collision.py --input prs.json  # offline
pytest -q tests/governance/test_pr_lane_collision.py
```

The detection core `detect_collisions(prs)` is pure and offline-testable; the
live mode reads open PRs via `gh`.

## Why CI runs the offline test, not the live scan per-PR

A per-PR blocking gate that scans *other* concurrently-open PRs would block your
PR for a collision you cannot fix from your own branch (the duplicate lives
elsewhere). That is an anti-pattern. So:

- **Blocking in CI:** the deterministic unit suite, which proves the detector
  flags the #1120/#1121 pair and rejects false positives.
- **Operator / scheduled:** the live `gh` scan, run when triaging open PRs (the
  same call this session used to confirm the duplicate was gone after #1121 was
  closed).

## Resolution rule (when a collision is found)

1. Compare the two diffs.
2. Choose one **canonical** PR — prefer stronger enforcement (fail-closed by
   default over opt-in) and provenance retention (do not delete the audit trail).
3. Close the weaker as **superseded**, recording the reason in a PR comment.
4. Never merge both. Arm auto-merge only on the canonical PR.
