# 00 — Thesis Statement

**Thesis class:** computational research infrastructure / software engineering for
scientific validity / falsifiable quantitative systems.

## Problem

Quantitative market-structure research is structurally prone to *false empirical
promotion*: a descriptive or admissibility result (a value computed, a test that
ran, a gate that passed) is silently re-narrated as a scientific claim
("validated", "profitable", "predictive edge"). The failure is not usually
fraud — it is the absence of a machine-checked boundary between *infrastructure
admissibility* and *empirical truth*. Prose drifts; numbers pass accidentally.

## Gap

Existing practice binds claims to evidence by convention (a reviewer, a README,
a notebook). Conventions are not fail-closed: they do not block a release, they
do not detect when a hash is stale, they do not refuse a claim whose falsifier
never ran. There is no widely-adopted, CI-enforced contract that makes an
unsupported empirical claim *un-mergeable*.

## Original contribution

A reference implementation in which **every claim is bound, by a fail-closed CI
gate, to eight artifacts**:

1. **invariant** — a stated property (`.claude/physics/INVARIANTS.yaml`, 108 entries);
2. **data source** — declared provenance (no ambient repo-root data assumptions);
3. **method** — the executable that computes the result;
4. **artifact** — a hashed, schema-valid output;
5. **falsifier** — an executable null/kill-test that *could* have refuted it
   (`governance/FALSIFIER_LEDGER.yaml`, 6 entries, each pinned to impl + test);
6. **replay path** — a command that reproduces the artifact from a clean tree;
7. **CI gate** — a required check that fails closed if any binding is missing;
8. **non-claim boundary** — an explicit statement of what is *not* asserted.

The contribution is the *binding mechanism*, not any market result. The system's
value is measured by what it **refuses to let pass**, not by what it predicts.

## Non-claims (binding)

This dissertation artifact makes **none** of the following claims:

- NO market alpha, edge, profitability, or predictive performance.
- NO claim that GeoSync's quantitative signals are empirically validated.
- NO claim of `B.wheel=0` (canonical packaging): the wheel still ships 13
  non-`geosync` legacy packages and carries 70 frozen latent-import debts
  (`artifacts/wheel_contract.json`, `--strict` verdict FAIL).
- NO claim of real L2 order-book empirical validation absent a recorded dataset
  + deterministic replay (status: HYPOTHESIS/OBSERVE only).
- NO claim that the governance prevents *all* false promotion — only that it
  converts a defined, enumerated class of it from convention to fail-closed gate.

## Artifact boundary

The unit of evaluation is the **repository and its CI**, not a market deployment.
"Truth" in this work means: *a claim's evidence binding is machine-verifiable and
its falsifier is executable* — i.e. **admissibility**, explicitly distinguished
from empirical/scientific truth. Promotion from admissibility to empirical claim
requires a separate, dataset-backed falsification study (see `05`), not performed
here.
