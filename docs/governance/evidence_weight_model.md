# GeoSync Evidence Weight Model

This document describes the calibration rules that bind the claim ledger
([`claim_ledger.md`](claim_ledger.md)) to the evidence available in the
repository. The companion machine-readable rules live at
[`.claude/evidence/EVIDENCE_MATRIX.yaml`](../../.claude/evidence/EVIDENCE_MATRIX.yaml)
and are validated by
[`validate_evidence.py`](../../.claude/evidence/validate_evidence.py).

The model exists because the 2026-04-26 audit produced two conflations
that recur across every supply-chain finding ever written:

- **F01:** range drift in `requirements.txt` was conflated with active
  vulnerable installation. The lower bound text said `torch>=2.1.0`; the
  resolver picked `torch==2.11.0`. Manifest text alone does not justify
  "actively vulnerable".
- **F03:** a vulnerable Strawberry version pinned in `requirements.lock`
  was conflated with a reachable auth-bypass exploit. `LOCKFILE_PIN` is
  not, by itself, evidence that the affected code path is reachable.

The matrix encodes those lessons as enforceable rules.

## How the model is structured

Two layers:

1. **Evidence categories** — 13 named kinds of evidence the repository
   produces (manifest text, lockfile pin, resolver output, scanner JSON,
   integration test, mutation result, etc.). Each has an ordinal strength
   band and an explicit list of claim tiers it can support, plus a list
   of overclaims it does NOT support.

2. **Prohibited overclaims** — named conflations a claim might attempt
   ("active vulnerable install", "exploit confirmed", "runtime
   reachable", "system is secure", …). Each names the evidence shape(s)
   that DO support it. A claim asserting an overclaim must rest on at
   least one of those shapes; otherwise the validator refuses it.

## Strength bands

Evidence strength is ordinal and documented:

| Band | What it means |
|---|---|
| `NONE` | No real evidence beyond rhetoric. |
| `WEAK` | Single declarative artefact; can be wrong about runtime. |
| `PARTIAL` | Multiple declarative artefacts, or one runtime artefact. |
| `STRONG` | Multiple runtime/executed artefacts that confirm one another at the same observation level. |
| `EXECUTED` | The claim was directly produced by running the code or measurement that the claim is about (no inference gap). |

The model intentionally refuses decimal scoring. Bands are ordinal because
ordinal × ordinal × ordinal does not produce a metric.

## The 13 evidence categories

| Category | Strength | Allowed tiers | Refuses |
|---|---|---|---|
| `FILE_DECLARATION` | WEAK | SPEC, EXTRAP, FACT (with companion) | active install, exploit, reachability |
| `LOCKFILE_PIN` | PARTIAL | SPEC, EXTRAP, FACT | exploit confirmed, reachability |
| `RESOLVER_OUTPUT` | STRONG | SPEC, EXTRAP, FACT | exploit, long-term resolution stability |
| `SCANNER_OUTPUT` | STRONG | SPEC, EXTRAP, FACT | exploit, reachability, scanner completeness |
| `RUNTIME_IMPORT_SMOKE` | PARTIAL | SPEC, EXTRAP, FACT (with companion) | behavioral correctness |
| `UNIT_TEST` | PARTIAL | SPEC, EXTRAP, FACT | exploit, integration correctness |
| `INTEGRATION_TEST` | STRONG | SPEC, EXTRAP, FACT | production correctness |
| `MUTATION_TEST` | STRONG | SPEC, EXTRAP, FACT | bug-free code |
| `CI_STATUS` | WEAK | SPEC, EXTRAP | runtime verification, security verification |
| `MANUAL_INSPECTION` | WEAK | SPEC, EXTRAP | reachability, active install, exploit |
| `EXTERNAL_ADVISORY` | STRONG | SPEC, EXTRAP, FACT | exploit, reachability |
| `BENCHMARK` | STRONG | SPEC, EXTRAP, FACT | production performance |
| `DATASET_RESULT` | STRONG | SPEC, EXTRAP, FACT | universal claim, production performance |

`FACT (with companion)` means the category alone is too weak for FACT,
but combining it with one of the listed companion categories is sufficient.
For example, a `FILE_DECLARATION` becomes FACT-grade only when paired with
`LOCKFILE_PIN`, `RESOLVER_OUTPUT`, or `SCANNER_OUTPUT`.

## The 14 prohibited overclaims

These are the conflations the model refuses. Each names the evidence
shapes that DO support it. If a claim asserts an overclaim, at least one
supporting shape must appear in the claim's `evidence_paths`; otherwise
the validator refuses the claim.

| Overclaim | Supported by | Lesson |
|---|---|---|
| `ACTIVE_VULNERABLE_INSTALL` | `RESOLVER_OUTPUT` ∪ `SCANNER_OUTPUT` ∪ `INTEGRATION_TEST` | F01: lower-bound text ≠ installed |
| `EXPLOIT_PATH_CONFIRMED` | `INTEGRATION_TEST` ∪ `DATASET_RESULT` (red-team) | F03: advisory ≠ reachable exploit |
| `RUNTIME_REACHABILITY` | `INTEGRATION_TEST` ∪ `RUNTIME_IMPORT_SMOKE` (covering route) | "I read the code" ≠ "I tried it" |
| `BEHAVIORAL_CORRECTNESS` | `INTEGRATION_TEST` ∪ `MUTATION_TEST` ∪ `DATASET_RESULT` | imports succeeding ≠ correct answer |
| `RUNTIME_VERIFICATION` | `INTEGRATION_TEST` ∪ `MUTATION_TEST` | green CI ≠ runtime correctness |
| `SECURITY_VERIFICATION` | `SCANNER_OUTPUT` ∪ `INTEGRATION_TEST` ∪ `EXTERNAL_ADVISORY` (paired) | "secure" is forbidden bare; use specifics |
| `PRODUCTION_PERFORMANCE` | `DATASET_RESULT` (production-like) | bench ≠ production |
| `UNIVERSAL_CLAIM` | `DATASET_RESULT` (cross-domain) | scientific overreach |
| `LONG_TERM_RESOLUTION_STABILITY` | `LOCKFILE_PIN` | resolver picks drift |
| `INTEGRATION_CORRECTNESS` | `INTEGRATION_TEST` | unit tests don't prove integration |
| `PRODUCTION_CORRECTNESS` | `DATASET_RESULT` (production data) | integration ≠ production |
| `BUG_FREE_CODE` | (nothing) | forbidden absolute |
| `SCANNER_COMPLETENESS` | (nothing) | scanners are bounded by their DB |

The two overclaims with no supporting evidence (`BUG_FREE_CODE`,
`SCANNER_COMPLETENESS`) are NEVER allowed; the validator refuses them
unconditionally with rule `OVERCLAIM_FORBIDDEN`.

## Why FACT requires a companion for some categories

`FILE_DECLARATION`, `RUNTIME_IMPORT_SMOKE`, and `CI_STATUS` are individually
too weak to anchor a FACT-tier claim:

- `FILE_DECLARATION` is intent, not behaviour. It must be paired with
  evidence that intent matches reality (`LOCKFILE_PIN`, `RESOLVER_OUTPUT`,
  `SCANNER_OUTPUT`).
- `RUNTIME_IMPORT_SMOKE` proves wiring, not behaviour. It must be paired
  with `UNIT_TEST` or `INTEGRATION_TEST`.
- `CI_STATUS` is a workflow result, not a contract. It must be paired
  with the underlying `INTEGRATION_TEST`, `MUTATION_TEST`, or `SCANNER_OUTPUT`
  it ran.

The matrix's `fact_requires_companion: true` flag, combined with
`fact_companion_categories`, encodes this explicitly. The validator
emits `FACT_COMPANION_REQUIRED` when the rule fires.

## Falsifier discipline

Every category has a `required_falsifier` field. A claim entering the
ledger that cites the category must specify a falsifier consistent with
that field. The shipping ledger entries already do this:

```yaml
- claim_id: SEC-DEP-STRAWBERRY-VERSION-RISK
  evidence_paths:
    - type: LOCKFILE_PIN
      ...
    - type: SCANNER_OUTPUT
      ...
    - type: EXTERNAL_ADVISORY
      ...
  falsifier: |
    Any lockfile entry strawberry-graphql<0.312.3, OR pip-audit reports
    GHSA-vpwc-v33q-mq89 / GHSA-hv3w-m4g2-5x77 against any locked manifest.
```

The falsifier names a concrete repository-observable condition that, if
ever true, falsifies the claim. This is the load-bearing piece of the
Popperian discipline: a claim without an observable falsifier is decoration.

## Worked examples

### F01 — correct framing (passes)

```python
check_claim_against_matrix(
    matrix,
    claim_class="SECURITY",
    tier="FACT",
    evidence_types=["FILE_DECLARATION", "RESOLVER_OUTPUT"],
    asserts=[],
)
# returns []  — claim is consistent
```

The claim asserts only what the cited evidence supports: that the manifest
declares a floor and the resolver picks a safe version today. It does not
assert active vulnerable install.

### F01 — wrong framing (refused)

```python
check_claim_against_matrix(
    matrix,
    claim_class="SECURITY",
    tier="FACT",
    evidence_types=["FILE_DECLARATION"],
    asserts=["ACTIVE_VULNERABLE_INSTALL"],
)
# returns [
#   ValidationError("ACTIVE_VULNERABLE_INSTALL", "OVERCLAIM_REFUSED",
#                   "asserting ACTIVE_VULNERABLE_INSTALL via FILE_DECLARATION
#                    requires at least one of [INTEGRATION_TEST,
#                    RESOLVER_OUTPUT, SCANNER_OUTPUT]")
# ]
```

### F03 — correct framing (passes)

```python
check_claim_against_matrix(
    matrix,
    claim_class="SECURITY",
    tier="FACT",
    evidence_types=["LOCKFILE_PIN", "SCANNER_OUTPUT", "EXTERNAL_ADVISORY"],
    asserts=[],
)
# returns []
```

The claim asserts only "the lockfile pins an above-floor version, and the
scanner agrees". No exploit claim.

### F03 — wrong framing (refused)

```python
check_claim_against_matrix(
    matrix,
    claim_class="SECURITY",
    tier="FACT",
    evidence_types=["LOCKFILE_PIN", "EXTERNAL_ADVISORY"],
    asserts=["EXPLOIT_PATH_CONFIRMED"],
)
# returns [
#   ValidationError("EXPLOIT_PATH_CONFIRMED", "OVERCLAIM_REFUSED",
#                   "asserting EXPLOIT_PATH_CONFIRMED requires at least
#                    one of [DATASET_RESULT, INTEGRATION_TEST]")
# ]
```

This is the F03 trap: the lockfile pin confirms version risk, but cannot
confirm an exploit. A live integration test (planned in issue #446) is
the only thing that can.

## Running the validator

```bash
# Validate the matrix file itself:
python .claude/evidence/validate_evidence.py

# Validate a specific claim shape from a script:
python - <<'PY'
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "ev", pathlib.Path(".claude/evidence/validate_evidence.py")
)
ev = importlib.util.module_from_spec(spec); spec.loader.exec_module(ev)
matrix = ev.load_matrix(pathlib.Path(".claude/evidence/EVIDENCE_MATRIX.yaml"))
errors = ev.check_claim_against_matrix(
    matrix,
    claim_class="SECURITY",
    tier="FACT",
    evidence_types=["LOCKFILE_PIN"],
    asserts=["EXPLOIT_PATH_CONFIRMED"],
)
print(errors)
PY
```

## Relation to other materials

- **`.claude/claims/CLAIMS.yaml`** — the actual claims, validated against this matrix
- **`.claude/claims/validate_claims.py`** — the claim-side validator (separate concern: schema, falsifier presence, etc.)
- **`tests/unit/governance/`** — the load-bearing tests that turn claims into FACT-tier
- **`docs/governance/audit_records/`** — the evidence artefacts cited from claims
- **`docs/governance/claim_ledger.md`** — the claim-side protocol document

## Limits of the model

The model does not:

- claim that satisfying the matrix proves the claim is true. It claims
  only that the claim is *consistent with the cited evidence*. Truth is
  the job of the test, not the validator.
- detect semantic vacuity. A test that asserts `True == True` will satisfy
  the schema; the human reviewer is responsible for ensuring the test
  actually tests the contract.
- handle the long tail of micro-claims in docstrings. The ledger is for
  high-impact claims (security/scientific/financial/reliability/etc.).
  Routine docstrings remain in code.

## Origin

Same arc as the claim ledger: introduced after the 2026-04-26 audit
codified that:

- A clean scanner output is not a security guarantee.
- A pinned vulnerable dependency is not a reachable exploit.
- A passing test suite is not a behavioural proof.
- A green CI badge is not runtime verification.

Each conflation is now refused by a rule with a name a future contributor
can grep for.
