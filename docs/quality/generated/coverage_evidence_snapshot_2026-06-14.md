# GeoSync Coverage Evidence Snapshot — 2026-06-14

Status: GENERATED_FROM_REPOSITORY_DATA
Verification tier: MACHINE_ASSISTED
Repository: neuron7xLab/GeoSync
Generated for: coverage engineering continuation and auditability

## Inputs used

This snapshot is derived from repository-declared quality contracts and coverage tooling, not from a freshly executed coverage run.

Authoritative inputs:

- `configs/quality/coverage_targets.toml`
- `tools/coverage/geosync_coverage_intelligence.py`
- `.github/workflows/coverage-ratchet-edges.yml`

## Global coverage policy

| Gate | Required |
|---|---:|
| Current release line coverage | 90% |
| Diff coverage | 90% |
| Final aspirational line coverage | 98% |

Interpretation:

- `90%` is the current release-quality floor.
- `98%` is the final aspirational target.
- Diff coverage is not optional; new production changes must remain covered.

## Surface contracts

| Surface | Paths | Short-term | Mid-term | Final | Risk |
|---|---|---:|---:|---:|---|
| core | `core/` | 80% | 90% | 95% | high |
| backtest | `backtest/` | 90% | 95% | 98% | critical |
| execution | `execution/` | 80% | 90% | 95% | critical |
| analytics | `analytics/` | 75% | 85% | 90% | medium |
| ingestion | `ingestion/`, `data/`, `core/data/` | 85% | 92% | 95% | high |
| risk | `risk/`, `execution/risk`, `core/risk` | 90% | 95% | 98% | critical |

## Coverage authority behavior

`tools/coverage/geosync_coverage_intelligence.py` is the single coverage authority for the repository. It is designed to reject fake confidence by validating raw evidence before trusting numbers.

Required evidence:

- `coverage.xml`
- `junit.xml`
- canonical `coverage_targets.toml`
- optional critical-surface and claim-falsifier contracts

Computed outputs:

- per-surface line coverage
- per-surface branch coverage
- global release coverage
- global branch coverage
- risk-weighted coverage score
- untested production files
- diff coverage for changed executable production lines
- claim-to-falsifier matrix

## Verdict model

| Verdict | Meaning |
|---|---|
| `MACHINE_VERIFIED` | Evidence is valid and every enforced gate passed. |
| `MACHINE_ASSISTED` | Gates may pass, but claim/mutation evidence is incomplete or execution proof is unavailable. |
| `HUMAN_REVIEW_ONLY` | Evidence is missing, stale, malformed, or empty; coverage numbers are not trusted. |

Exit-code policy:

| Code | Meaning |
|---:|---|
| 0 | Requested gates accepted. |
| 1 | Coverage gate failed. |
| 2 | Claim falsifier matrix incomplete under claim enforcement. |
| 3 | Evidence invalid; fail closed. |

## Ratchet edge gate

A dedicated GitHub Actions gate exists for coverage-ratchet falsifiers:

```bash
python -m pytest tests/tools/test_coverage_intelligence_ratchet_edges.py -q -p no:cacheprovider
```

Workflow: `.github/workflows/coverage-ratchet-edges.yml`

The gate runs on:

- pull requests to `main` touching coverage/tooling paths
- pushes to `main` touching coverage/tooling paths
- manual dispatch

## Current generated conclusion

The repository now has a declared coverage governance model, risk-weighted surface targets, a coverage-intelligence authority, and a dedicated ratchet-edge workflow.

This snapshot does not claim a current numeric coverage percentage because no fresh `coverage.xml` and `junit.xml` execution artifacts were produced by this generation step.

Correct status is therefore:

```text
MACHINE_ASSISTED
```

A future run may upgrade the status to `MACHINE_VERIFIED` only if the coverage authority receives valid, non-stale evidence and all enforced gates pass.

## Next deterministic upgrade

Generate fresh evidence and run the authority:

```bash
make coverage-baseline
python -m tools.coverage.geosync_coverage_intelligence \
  --coverage-xml reports/coverage/coverage.xml \
  --junit-xml reports/junit.xml \
  --targets configs/quality/coverage_targets.toml \
  --enforce-release \
  --enforce-diff
```

Acceptance criteria:

- evidence is present and non-empty;
- evidence is not stale against measured source files;
- release coverage is at least 90%;
- diff coverage is at least 90%;
- critical execution/risk/backtest surfaces do not silently degrade;
- verdict is `MACHINE_VERIFIED` or the run fails closed with a specific reason.
