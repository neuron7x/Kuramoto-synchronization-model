# False-confidence detector

Source-of-truth: [`tools/audit/false_confidence_detector.py`](../../tools/audit/false_confidence_detector.py)
Tests: [`tests/audit/test_false_confidence_detector.py`](../../tests/audit/test_false_confidence_detector.py)

## Why this exists

A repository can pass every linter, every test, and every scanner while
still being structurally wrong about itself:

- a coverage badge can show 90% on a config that excludes most of the source
- a security-deep workflow can be green while a Dockerfile installs an
  un-audited manifest
- a doc can claim "import-linter enforces module boundaries" while no
  `.importlinter` exists
- a validator file can sit unwired in CI

Each of these is a **false-confidence zone**: a place where the *appearance*
of correctness exceeds the *evidence* for it. The detector surfaces them
mechanically.

## Ten detector classes

| ID | Class | Lesson |
|---|---|---|
| **C1** | `COVERAGE_OMISSION_RISK` | F02 — `.coveragerc` omits more than it covers. |
| **C2** | `SCANNER_PATH_MISMATCH` | F01 / F03 — security scanner runs on a manifest that production does not install. |
| **C3** | `TEST_NAME_OVERCLAIM` | A test named `test_secure_*` with one assertion is heuristic theatre. |
| **C4** | `DOCUMENTATION_OVERCLAIM` | Docs reference an enforcer file that does not exist. |
| **C5** | `VALIDATOR_EXISTENCE_ONLY` | A validator file ships but no CI workflow invokes it. |
| **C6** | `DEPENDENCY_MANIFEST_DRIFT` | Pointer to the dependency-truth unifier; this detector does not duplicate that logic. |
| **C7** | `CI_PATH_MISMATCH` | Workflow named "test/ci/lint/security" with a narrow `paths:` filter. |
| **C8** | `TYPE_IGNORE_CONCENTRATION` | More than 8 `# type: ignore` directives in one file. |
| **C9** | `NO_COVER_CONCENTRATION` | More than 8 `# pragma: no cover` directives in one file. |
| **C10** | `BROAD_EXCEPTION_CONCENTRATION` | More than 5 `except Exception:` catches in one file. |

## Output

Deterministic JSON. Each finding records:

```json
{
  "finding_id": "C1-COVERAGERC-OMIT-INFLATION",
  "false_confidence_type": "C1",
  "evidence_path": ".coveragerc",
  "apparent_claim": "...",
  "actual_evidence": "...",
  "risk": "CRITICAL | HIGH | MEDIUM | LOW",
  "priority": "CRITICAL | HIGH | MEDIUM | LOW",
  "minimal_repayment_action": "..."
}
```

## Running

```bash
# Report-only (always exits 0):
python tools/audit/false_confidence_detector.py

# Gate mode (exits non-zero if any finding):
python tools/audit/false_confidence_detector.py --exit-on-finding

# Persist:
python tools/audit/false_confidence_detector.py --output reports/false-conf.json
```

## What the live tree shows (2026-04-26 baseline)

| Class | Count | Notable |
|---|---|---|
| C1 | 1 | `.coveragerc`: 29 omits vs 3 sources (9.7×) — F02 closure not in main yet |
| C2 | 3 | coherence_bridge / cortex_service / sandbox Dockerfiles install `requirements.txt`; only `requirements.lock` is pip-audited |
| C3 | 11 | heuristic-grade test-name overclaim flags |
| C5 | 3 | the validators introduced by this calibration layer ship UNWIRED — CI integration is the load-bearing follow-up |
| C6 | 1 | pointer to dep-truth unifier |
| C8 | 11 | files with ≥8 `# type: ignore` (concentration trap) |
| C9 | 20 | files with ≥8 `# pragma: no cover` (concentration trap) |
| C10 | 25 | files with ≥5 broad-exception catches |

C4 and C7 currently do not fire on the live tree — that is the desired
state for those classes. The synthetic tests in
`tests/audit/test_false_confidence_detector.py` prove the detectors fire
when the patterns appear.

## Thresholds

| Detector | Threshold | Rationale |
|---|---|---|
| C1 | `omit_count >= 2 * source_count` | Strong signal that the omits invalidate the source declaration. |
| C8 | 8 | Empirically separates targeted suppressions from systemic typing surrender. |
| C9 | 8 | Same logic for coverage-pragma. |
| C10 | 5 | Lower because each broad catch silently eats one entire failure class. |

Adjusting a threshold downward catches more zones but increases false
positives. Tune with care; record the rationale in this doc.

## Constraints (what the detector deliberately is NOT)

- It is not a security scanner. It does not look at advisory databases.
- It is not a test-quality checker. C3 is heuristic; pair with mutation
  testing for real proof that a test catches what it claims to catch.
- It is not a coverage tool. C1 and C9 surface configuration risks; the
  actual coverage % is computed by `coverage.py`.
- It does not call AST/Tree-sitter. All detection is line-grep based,
  which makes it fast and language-portable but accepts some noise.

## Wiring into CI (next step)

The right way to wire this in:

```yaml
# .github/workflows/false-confidence.yml (proposed; not in this PR)
name: false-confidence
on: [pull_request]
jobs:
  detect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
      - run: python tools/audit/false_confidence_detector.py --output reports/fc.json
      - uses: actions/upload-artifact@v4
        with:
          name: false-confidence-report
          path: reports/fc.json
      # Note: --exit-on-finding is intentionally NOT used; the report is
      # advisory until the team has paid down the C1/C5/C8/C9/C10 backlog.
      # Flip to --exit-on-finding once the live tree reports zero.
```

This staged approach (advisory now, gating later) matches the calibration
philosophy: TRACK the thing first, then enforce.

## Origin

Same arc:

- F01 / F02 / F03 produced the initial palette (C1, C2, C8, C9).
- Writing the calibration layer surfaced four more (C5, C6, C7) when we
  noticed our own validators would otherwise ship unwired.
- C3 / C4 / C10 cover the classic ways docs and tests can lie.
