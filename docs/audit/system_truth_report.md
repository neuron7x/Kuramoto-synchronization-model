# System truth report

Source-of-truth: [`tools/audit/system_truth_report.py`](../../tools/audit/system_truth_report.py)
Tests: [`tests/audit/test_system_truth_report.py`](../../tests/audit/test_system_truth_report.py)

## Why this exists

The calibration layer ships eight independent subsystems:

- claim ledger (`.claude/claims/`)
- evidence matrix (`.claude/evidence/`)
- dependency-truth unifier (`tools/deps/`)
- false-confidence detector (`tools/audit/false_confidence_detector.py`)
- security reachability graph (`tools/security/`)
- architecture boundaries (`.importlinter`)
- mutation kill ledger (`.claude/mutation/MUTATION_LEDGER.yaml`)
- physics invariants (`.claude/physics/INVARIANTS.yaml`)

Each subsystem answers ONE question. The system truth report aggregates
their answers into a single deterministic dashboard so a human can read
the state of the calibration layer in 30 seconds.

## Bands

Ordinal, four values:

| Band | Means |
|---|---|
| `GREEN` | nothing actionable in this subsystem |
| `YELLOW` | actionable but TRACKED on a backlog |
| `RED` | actionable, NOT tracked, gate failing or ready to fail |
| `UNKNOWN` | data unavailable (subsystem not run, file missing, parse error) |

There is no decimal score. Bands are ordinal.

## Output

Two artefacts per run:

- **`/tmp/geosync-system-truth.json`** — deterministic JSON for machines
- **Markdown** — rendered to stdout (or to `--md-output` path) for humans

```bash
# Default: JSON to /tmp/geosync-system-truth.json, Markdown to stdout:
python tools/audit/system_truth_report.py

# Persist both:
python tools/audit/system_truth_report.py \
    --json-output reports/system-truth.json \
    --md-output  reports/system-truth.md

# Gate mode:
python tools/audit/system_truth_report.py --exit-on-red
```

The aggregator always exits 0 in report-only mode. Use `--exit-on-red`
to gate CI on overall band == RED.

## Section list (deterministic order)

| # | Section | Source |
|---|---|---|
| 1 | `claim_ledger` | `.claude/claims/CLAIMS.yaml` |
| 2 | `evidence_matrix` | `.claude/evidence/EVIDENCE_MATRIX.yaml` |
| 3 | `dependency_truth` | `tools/deps/validate_dependency_truth.py` |
| 4 | `false_confidence` | `tools/audit/false_confidence_detector.py` |
| 5 | `reachability` | `tools/security/reachability_graph.py` |
| 6 | `architecture_boundaries` | `lint-imports` against `.importlinter` |
| 7 | `mutation_kill` | `.claude/mutation/MUTATION_LEDGER.yaml` |
| 8 | `physics_invariants` | `.claude/physics/INVARIANTS.yaml` |

Sections are sorted alphabetically in the output (lexicographic on
section name) for byte-deterministic diffs.

## Live tree band snapshot (2026-04-26)

| Section | Band | Notes |
|---|---|---|
| claim_ledger | YELLOW | One PARTIAL claim (`SEC-GRAPHQL-WS-AUTHN-REACHABILITY`); follow-up #446 |
| evidence_matrix | GREEN | self-validation clean |
| dependency_truth | RED | 3 actionable D2 drifts (fastapi/prom-client/uvicorn in scan.lock) |
| false_confidence | RED | C1 fires (.coveragerc); plus C8/C9/C10 backlog concentrations |
| reachability | YELLOW | 2 advisories at AUTH_SURFACE_PRESENT; followup #446 |
| architecture_boundaries | GREEN | 5 contracts kept, 0 broken |
| mutation_kill | GREEN | 10 mutants in ledger, 4 calibration mutants killed end-to-end |
| physics_invariants | GREEN | 87 invariants registered |
| **overall_band** | **RED** | dependency_truth or false_confidence drives RED |

## Next repayment PRs

The aggregator synthesises a deterministic queue of up to 10 repayment
items, derived directly from section state:

```
1. [CRITICAL] Rebuild .coveragerc to honestly measure coverage (F02)
2. [HIGH]     Pay down actionable D2/D4/D5 manifest drifts
3. [HIGH]     Close PARTIAL claim SEC-GRAPHQL-WS-AUTHN-REACHABILITY
4. [HIGH]     Resolve reachability for GHSA-vpwc-v33q-mq89 (issue #446)
5. [HIGH]     Resolve reachability for GHSA-hv3w-m4g2-5x77 (issue #446)
6. [MEDIUM]   Reduce C10 concentrations (25 files)
7. [MEDIUM]   Reduce C9 concentrations (20 files)
8. [MEDIUM]   Reduce C3 concentrations (11 files)
9. [MEDIUM]   Reduce C8 concentrations (11 files)
10.[MEDIUM]   Reduce C2 concentrations (3 files)
```

This list is the calibration layer's executable backlog. It is NOT a
roadmap; it is the ordered set of next-actions whose completion would
move at least one band from RED → YELLOW or YELLOW → GREEN.

## Determinism guarantees

- Same code + same data → byte-identical JSON
- Section order: alphabetical
- Within sections: dictionaries are sorted by key
- Drift / finding lists: sorted by structural key (not by discovery time)
- Repayment queue: priority-ordered, then deterministic by source
- No timestamps in the output

## What the aggregator does NOT do

- It does NOT compute a numeric "health score". Bands only.
- It does NOT recommend specific code changes. The `next_repayment_prs`
  list names the area but not the patch.
- It does NOT guarantee that GREEN means "correct". GREEN means "no
  signal observed by the gates we have built". The whole point of the
  calibration layer is to grow the set of gates so GREEN keeps getting
  closer to "correct".
- It does NOT replace the underlying tools. Always run them directly
  for the full diagnostic; the aggregator surfaces a summary.

## Limits and known imprecisions

- `architecture_boundaries` requires `lint-imports` on PATH; if the CLI
  is missing, the section reports UNKNOWN.
- `reachability` uses line-grep AST analysis; it under-reports exotic
  factory chains. Treat low-tier results as a floor.
- `false_confidence` C3 (test-name overclaim) is heuristic-grade.
- The `overall_band` aggregation uses the worst-band rule. UNKNOWN
  outranks RED so a missing subsystem is louder than a RED one;
  a clean tree therefore requires every subsystem to report GREEN.

## Wiring into CI (proposed; not in this PR)

```yaml
# .github/workflows/system-truth.yml
name: system-truth
on: [pull_request]
jobs:
  truth:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
      - run: pip install pyyaml import-linter
      - run: python tools/audit/system_truth_report.py \
                 --json-output reports/system-truth.json \
                 --md-output reports/system-truth.md
      - uses: actions/upload-artifact@v4
        with:
          name: system-truth
          path: reports/system-truth.*
      # Note: --exit-on-red is intentionally NOT used yet. The dashboard
      # is advisory until the live tree's RED bands are paid down.
      # Flip to --exit-on-red once dependency_truth + false_confidence
      # both report YELLOW or better.
```

This staged approach matches the calibration philosophy: TRACK the
thing first, then ENFORCE.

## Origin

Same arc:

- The 2026-04-26 audit produced a 18-finding report. Each finding
  belonged to a different subsystem.
- The calibration layer turned each subsystem into a small
  per-subsystem validator.
- The truth report binds them into a single deterministic dashboard so
  the question "what is the state of the calibration layer right now?"
  has a single, machine-readable answer.
