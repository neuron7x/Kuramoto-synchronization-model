<!--
Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
SPDX-License-Identifier: MIT
-->
# Preregistration Policy (RES-002)

## Purpose

GeoSync promotes exactly one **flagship** research question
(`research/flagship/rq.yaml` — `FLAGSHIP-RQ-001`, RES-001, merged). This policy
requires that its analysis plan be **frozen and tamper-evident before any run**,
so results cannot be reverse-engineered from a plan quietly edited after the fact.

The preregistration lives in `protocols/flagship_preregistration.yaml`
(`FLAGSHIP-PREREG-001`) and is enforced by the fail-closed gate
`scripts/ci/check_preregistration.py` (tests in `tests/ci/test_preregistration.py`).

## Boundary (inherited, unchanged)

This preregisters an **infrastructure / synthetic-only** question:
wheel-contract reproducibility read from repository and build artifacts, at
`tier: HYPOTHESIS`, under `RESEARCH_ALPHA_SYNTHETIC_ONLY_NO_DEPLOY`.

It makes **no empirical or market claim**, asserts **no out-of-sample edge**, and
**no empirical/market run is claimed** by registering it. Outcomes are
integer/boolean repository observables only (never returns, PnL, Sharpe, or edge).
See `PRODUCT_CATEGORY.md` and `FORBIDDEN_CLAIMS.md`.

## Required sections (frozen before any run)

All live inside `protocol_body` and every one must be present and non-empty:

| Section | Fixes |
| --- | --- |
| `hypotheses` | H1 (alternative) and H0 (null), directionality, unit of analysis |
| `primary_outcomes` | the single primary decision variable (`D_marginal`) + threshold |
| `secondary_outcomes` | descriptive-only observables (reproducibility, total D) |
| `dataset_versions` | pinned commit / snapshot; the "dataset" is a build artifact, not market data |
| `exclusions` | what is out of scope (third-party, optional imports, test-only, market data) |
| `splits` | within-snapshot comparator-vs-intervention design; reruns; no peeking |
| `nulls` | the null hypothesis and its reference (pre-existing gate suite) |
| `baselines` | the comparator instrument and contrast |
| `metrics` | exact formulas; no return/edge metric admissible |
| `multiple_testing_corrections` | none required (single primary hypothesis) + rationale |
| `stopping_rules` | full-enumeration pass; fixed rerun count; no optional stopping |
| `promotion_rules` | HARD_PASS / HARD_FAIL criteria; promotion stays within boundary |

## Tamper-evidence contract

1. **Content digest.** `digest` = SHA-256 over the **canonical** serialization of
   `protocol_body` — JSON with sorted keys, compact separators, UTF-8
   (`digest_algo: sha256`, `digest_canonicalization: json-sortkeys-compact-utf8`).
   The canonical form is independent of YAML whitespace or key order, yet any
   change to a body **value** changes the digest.
2. **The gate verifies the digest matches the body.** A single mutated body byte
   without a re-derived digest is a mismatch → non-zero exit.
3. **Deterministic date.** `prereg_date` is the fixed string `2026-07-19`; it is
   **never** derived from `datetime.now()`, so the digest is reproducible
   bit-for-bit.

## Deviations are append-only, never overwritten

The `deviations` list lives **outside** the hashed `protocol_body` — appending a
deviation does not touch (or silently mask) the frozen plan or its digest.

- Each entry carries `seq`, `date`, `reason`, `decision`.
- `seq` values are **strictly increasing and contiguous from 1**. Deleting or
  reordering an entry leaves a gap and fails the gate.
- You **never** edit the frozen `protocol_body` to reflect a change of plan.
  You append a deviation describing it.

## Changing the frozen plan requires a NEW study

Per the RQ scope-lock (`scope_change_requires_new_study: true`), altering the
frozen plan after preregistration invalidates it. A genuine change of scope,
comparator, or criteria requires a **new `prereg_id` and a new study id** — not an
in-place edit of `FLAGSHIP-PREREG-001`. Re-deriving the digest is only for
authoring/rotating the plan under a new id, never for post-hoc reblessing.

## Re-deriving the digest (authoring only)

```bash
python -c "import yaml, scripts.ci.check_preregistration as g; \
  print(g.compute_digest(yaml.safe_load( \
  open('protocols/flagship_preregistration.yaml'))['protocol_body']))"
```

Paste the output into the `digest:` field. A companion `.sha256` file is an
acceptable alternative carrier; this policy uses the inline `digest:` field.

## Running the gate

```bash
python -m scripts.ci.check_preregistration          # exit 0 = intact
python -m scripts.ci.check_preregistration --json    # machine-readable verdict
python -m pytest tests/ci/test_preregistration.py -q # positive + negative closure
```

Exit codes: `0` intact · `1` missing section / digest mismatch / deviation-order
violation · `2` missing or malformed file (fail-closed).
