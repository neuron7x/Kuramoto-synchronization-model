# IERD-PAI-FPS-UX-001 — Institutional Engineering Remediation Directive

**Status.** Binding standard for GeoSync as of 2026-05-03.
**Adoption.** [ADR 0020](../adr/0020-ierd-adoption.md).
**Ledger.** [`docs/CLAIMS.yaml`](../CLAIMS.yaml) (extended schema v2 with `tier`).
**CI gate.** [`scripts/ci/check_claims.py`](../../scripts/ci/check_claims.py) + [`scripts/ci/lint_forbidden_terms.py`](../../scripts/ci/lint_forbidden_terms.py).

---

## 1. Scope

This directive applies to: documentation, CI pipeline, API layer, frontend integration layer, validation framework, and **every claim** using the terms

```
physics-aligned · first-principles · truth · energy · law ·
invariant · production-ready · UX-ready · cycle-time acceleration
```

A claim is admitted to ANCHORED state only when it has:

```
1. explicit equation or specification mapping
2. invariant test
3. convergence or stability evidence
4. traceable evidence_id (CLAIMS.yaml entry)
5. CI enforcement
```

## 2. Claim tier standard

| Tier | When allowed | Required evidence |
|---|---|---|
| **ANCHORED** | All gates pass | `file`, line range, equation/spec, test_id, CI run |
| **EXTRAPOLATED** | Partial evidence | known evidence + named missing evidence + confidence |
| **SPECULATIVE** | Research only | hypothesis only; **forbidden** in README, product docs, API docs, reports |
| **UNKNOWN** | No evidence | must have a tracking issue |

Every claim in README, docs, comments, docstrings, reports, API descriptions carries a tier. The tier lives in `docs/CLAIMS.yaml`; the surface text either carries the tier directly or links to the claim_id.

## 3. Forbidden terminology and required replacements

`scripts/ci/lint_forbidden_terms.py` enforces:

| Forbidden | Replacement (unless evidence anchors literal use) |
|---|---|
| `truth function` | `objective criterion` |
| `energy` (rhetorical) | `phase potential` (unless physically derived from H, U, F, S) |
| `serotonin_gain` | `coupling_gain` |
| `law` (rhetorical) | `tested invariant` (unless physically proven and cited) |
| `thermodynamic` (rhetorical) | `stability-like` (unless thermodynamic variables exist) |
| `neuro` (rhetorical) | `neuro-inspired` (unless biological model exists and cited) |
| `physics-aligned production-ready` | (split + tier-label both halves) |
| `first-principles` (uncited) | `derived from <equation/spec>` with citation |

Any term in §3 may be used **literally** if it is anchored by a citation (see `docs/BIBLIOGRAPHY.md`, `docs/CITATION_MAP.md`) and a falsifying test (`tests/`).

## 4. Definition of Done (institutional)

A module is **DONE** only if it has all of:

```
1. equation or specification mapping
2. dimensional test (or equivalent type/contract test)
3. invariant test (conservation / monotonic / stability)
4. analytical or limit-case test
5. convergence or stability evidence
6. ADR (docs/adr/NNNN-...)
7. API contract if exposed (OpenAPI / proto)
8. UX state contract if user-facing
9. edge-case tests
10. traceable claim ledger entry (CLAIMS.yaml)
```

Anything below this state is **not** production-ready and must not be described as such in user-facing surfaces.

## 5. Metric thresholds

| Metric | Threshold | Source |
|---|---|---|
| **PAI** (Physics Alignment Index) | ≥ 0.90 | `docs/validation/pai_report_*.md` |
| **FPS_audit** (claim ledger evidence coverage) | = 1.00 | `docs/CLAIMS.yaml` × `check_claims.py` |
| **5-step coverage** (ADR + convergence) | ≥ 0.90 | `docs/adr/` × convergence tests |
| **API contract** | green | Schemathesis / Dredd |
| **UXRS** (UX readiness) | ≥ 0.95 | endpoint × declared states |
| **E2E latency budget** | all 4 layers green | Lighthouse + OTel |
| **ECC** (edge-case coverage) | ≥ 0.90 | matrix × tests |

## 6. Governance

A merge is blocked if:

1. a physics claim lacks an invariant test
2. an ANCHORED claim lacks `evidence_id`
3. an exposed endpoint lacks schema
4. an error state lacks envelope
5. an edge case lacks test
6. a latency budget regresses
7. documentation contains forbidden terminology without evidence anchor

## 7. Phased adoption

* **Phase 0 (this PR).** Directive published; CLAIMS.yaml extended with `tier`; lint published in **warn** mode; README + reports surface terminology audited; first PAI snapshot frozen.
* **Phase 1.** PAI ≥ 0.90 reached on `core/kuramoto`, `core/ricci`, `core/temporal`. FPS_audit = 1.00 enforced.
* **Phase 2.** ADRs + convergence tests for every numerical module. 5-step coverage ≥ 0.90.
* **Phase 3.** OpenAPI 3.1 + JSON Schema for every exposed endpoint. Async simulation workflow. Standard error envelope.
* **Phase 4.** UXRS ≥ 0.95. E2E latency budgets green. ECC ≥ 0.90.
* **Phase 5.** Lint moves from **warn** to **fail-closed**.

## 8. Source

Directive originates from external falsification audit (Yana Levchyshyna, 2026-05-02) of GeoSync's "physics-aligned / production-ready" claims. Response is logged in [`docs/yana-response.md`](../yana-response.md).
