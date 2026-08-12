# GeoSync Claim Ledger

The claim ledger is GeoSync's structured record of every high-impact
repository claim — security, scientific, financial, reliability,
reproducibility, performance, architecture, governance — together with the
evidence, tests, falsifiers, and owners that turn each claim into something
the system itself can defend.

## Why this exists

A repository accumulates claims faster than it accumulates tests. README
prose says "secure", a docstring says "fast", a CI badge says "passing", and
a research paper says "novel" — but none of these are mechanically defended
unless something in the codebase fails the moment the claim becomes false.

The ledger forces every active claim to satisfy six conditions:

1. **Statement** — what is being claimed, in plain English.
2. **Class** — which axis the claim lives on (SECURITY, SCIENTIFIC, …).
3. **Tier** — strength of the claim (FACT, EXTRAPOLATION, SPECULATION).
4. **Evidence** — concrete artefacts that support the tier.
5. **Falsifier** — the explicit condition that, if observed, falsifies the claim.
6. **Owner surface** — the directory or subsystem that owns repair when the
   claim breaks.

Claims without these are not claims; they are decoration. The validator
([`validate_claims.py`](../../.claude/claims/validate_claims.py)) refuses to
accept them.

## File layout

| Path | Role |
|---|---|
| `.claude/claims/CLAIMS.yaml` | The ledger itself. Source of truth. |
| `.claude/claims/validate_claims.py` | Stdlib + PyYAML validator. CI-ready. |
| `tests/unit/claims/test_validate_claims.py` | Tests for the validator (positive + injection). |
| `tests/unit/governance/test_dependency_floor_alignment.py` | Test that backs `SEC-DEP-TORCH-RANGE-DRIFT` and `SEC-DEP-STRAWBERRY-VERSION-RISK`. |
| `docs/governance/audit_records/` | Audit-record evidence files referenced from `evidence_paths`. |

## Schema

```yaml
schema_version: 1

claims:
  - claim_id: SEC-EXAMPLE
    statement: "Plain-English description of what is asserted."
    class: SECURITY            # or SCIENTIFIC / FINANCIAL / RELIABILITY /
                               # REPRODUCIBILITY / PERFORMANCE /
                               # ARCHITECTURE / GOVERNANCE
    tier: FACT                 # or EXTRAPOLATION / SPECULATION
    evidence_paths:
      - type: LOCKFILE_PIN     # one of the 13 evidence categories
        path: requirements.lock
        capture: "<exact line or short summary>"
    test_paths:
      - tests/unit/governance/test_some_contract.py
    falsifier: |
      Any pip-audit run on requirements.lock reports advisory X.
    owner_surface: deps/python/runtime
    last_verified_command: |
      pip-audit -r requirements.lock --no-deps -f json
    status: ACTIVE             # or PARTIAL / RETIRED / REJECTED
    related_pr: 445             # optional
    related_issue: 446          # optional
    non_testable_reason: ""    # optional; required when test_paths is empty
                               #           on a FACT-tier claim
    rejection_reason: ""       # required when status == REJECTED
```

### Tier semantics

| Tier | Required evidence | Required test | Closure |
|---|---|---|---|
| `FACT` | ≥ 1 evidence path; for SECURITY needs at least one of SCANNER_OUTPUT, EXTERNAL_ADVISORY, LOCKFILE_PIN, FILE_DECLARATION, RESOLVER_OUTPUT | ≥ 1 test path **OR** explicit `non_testable_reason` | gate validates clean |
| `EXTRAPOLATION` | ≥ 1 evidence path | optional | gate validates clean if falsifier + owner present |
| `SPECULATION` | optional | optional | gate validates clean (kept as flag for follow-up) |

### Status semantics

| Status | Behaviour |
|---|---|
| `ACTIVE` | Currently asserted. Validator gates apply. |
| `PARTIAL` | Closure incomplete (e.g. follow-up issue open). Validator still gates. |
| `RETIRED` | Superseded. Kept for audit trail. Gates do not apply. |
| `REJECTED` | Claim falsified. **Required** to keep as negative reference so the same overclaim does not return. `rejection_reason` is mandatory. |

### Evidence categories (13)

These mirror the categories defined in
[`evidence_weight_model.md`](evidence_weight_model.md):

```
FILE_DECLARATION   LOCKFILE_PIN       RESOLVER_OUTPUT
SCANNER_OUTPUT     RUNTIME_IMPORT_SMOKE
UNIT_TEST          INTEGRATION_TEST   MUTATION_TEST
CI_STATUS          MANUAL_INSPECTION  EXTERNAL_ADVISORY
BENCHMARK          DATASET_RESULT
```

Each category has a defined evidence-strength band and a list of allowed
claim tiers. The companion `validate_evidence.py` validator cross-checks
ledger entries against the matrix.

## Running the validator

```bash
# Validate the shipping ledger:
python .claude/claims/validate_claims.py

# Validate a candidate ledger before committing:
python .claude/claims/validate_claims.py --ledger /tmp/proposed-CLAIMS.yaml

# CI / pre-commit hook:
python .claude/claims/validate_claims.py || exit 1
```

Exit code is `0` when the ledger is clean, `1` otherwise. The validator
prints one line per validation error so log-scrapers can parse it.

## Workflow

### Adding a claim

1. Write the claim in `CLAIMS.yaml` with `tier: SPECULATION` first.
2. Add the evidence file(s) under `docs/governance/audit_records/` or
   reference an existing artefact.
3. Promote to `EXTRAPOLATION` once at least one evidence path is in place.
4. Promote to `FACT` only after a falsifier-aware test exists in
   `tests/unit/...` or `tests/integration/...`. The test is the load-bearing
   contract; without it, the claim cannot be FACT.
5. Run `python .claude/claims/validate_claims.py` locally before commit.

### Falsifying a claim

If the claim turns out to be wrong:

1. Move the entry to `status: REJECTED`.
2. Add `rejection_reason` describing what falsified it (point to the audit
   record or PR that did the work).
3. **Do not delete the entry.** Negative references prevent the same
   overclaim from re-emerging; the validator's `REJECTED` rule keeps them
   intact.

### Evolving a claim

If a claim is replaced by a stronger version:

1. The original entry moves to `status: RETIRED`.
2. The new entry uses a fresh `claim_id`.
3. `RETIRED` claims do not gate but their evidence paths still must exist
   (so the audit trail remains navigable).

## Forbidden patterns

The validator and the companion evidence matrix together refuse the
following anti-patterns:

| Anti-pattern | Refusing rule |
|---|---|
| FACT tier with no `evidence_paths` | `FACT_NO_EVIDENCE` |
| FACT tier with no `test_paths` and no `non_testable_reason` | `FACT_NO_TEST` |
| SECURITY/FACT relying on `MANUAL_INSPECTION` alone | `SECURITY_FACT_INSUFFICIENT_EVIDENCE` (the F03 trap) |
| SCIENTIFIC claim with no falsifier | `SCIENTIFIC_NO_FALSIFIER` |
| PERFORMANCE/FACT without `BENCHMARK` or `DATASET_RESULT` | `PERFORMANCE_FACT_NO_BENCHMARK` |
| Evidence path that does not exist on disk | `EVIDENCE_PATH_NOT_FOUND` |
| Duplicate `claim_id` | `DUPLICATE_CLAIM_ID` |
| Unknown evidence type (e.g. "ASTROLOGICAL_HUNCH") | `EVIDENCE_TYPE_UNKNOWN` |
| `REJECTED` status with no `rejection_reason` | `REJECTED_NO_REASON` |
| Universal scientific claims (e.g. "X always holds") without cross-domain evidence | rejected at review; encode as `SPECULATION` until cross-domain dataset present |

## What the ledger explicitly does NOT do

- It does **not** replace the test suite. Tests remain the runtime contract.
- It does **not** quantify "debt" or risk on a numeric scale. It uses
  ordinal categories and refuses decimal scores.
- It does **not** convert advisory presence into exploitability. Reachability
  is a separate evidence axis (see `SEC-GRAPHQL-WS-AUTHN-REACHABILITY` for
  the canonical worked example).
- It does **not** auto-generate claims from code. Each entry is a deliberate
  human assertion that the validator then mechanically defends.

## Related governance materials

- `.claude/evidence/EVIDENCE_MATRIX.yaml` — evidence-strength rules
- `docs/governance/evidence_weight_model.md` — per-category usage rules
- `docs/governance/audit_records/` — referenced audit artefacts
- `tests/unit/governance/` — claim-backing governance tests

## Origin

This ledger was introduced after the 2026-04-26 reverse-extrapolative
technical-debt audit and the F01/F03 supply-chain investigation. The audit
established that:

- A "decimal debt score" was epistemic theatre.
- A scanner-clean lock file was not the same as a verified deploy.
- A vulnerable package version was not the same as a reachable exploit.

The ledger is the calibration mechanism that prevents those conflations
from recurring.
