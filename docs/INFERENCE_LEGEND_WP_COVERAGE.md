# Inference-Legend Work-Package Coverage Ledger

Companion to [`INFERENCE_LEGEND_EXIT_WORK_ACT.md`](INFERENCE_LEGEND_EXIT_WORK_ACT.md).

The act lists ten work packages. Most are **not greenfield**: GeoSync already
ships substantial substrate for them. This ledger records, per package, the
existing artifacts that implement it and the gaps that remain, so the act binds
to the repository instead of re-creating a parallel stack.

It makes **no scientific claim**. It asserts structural correspondence between
the act and the tree, machine-checked by
[`tools/inference/check_wp_coverage.py`](../tools/inference/check_wp_coverage.py)
(fail-closed: an `EXISTS`/`PARTIAL` package that cites a vanished artifact, or a
`GAP` package that lists code, fails the gate). The predictive rank of the
project is unchanged by this document — current status remains
**HYPOTHESIS-tier with strong governance and incomplete predictive proof**, per
the act.

## Status

`EXISTS` — substantive implementation present. `PARTIAL` — components present
but the package's binding/contract is incomplete. `GAP` — not implemented.

| WP | Title | Status | Anchor artifacts (non-exhaustive) |
|----|-------|--------|------------------------------------|
| WP-01 | Contextualization frame | PARTIAL | `schemas/inference/context_manifest.schema.json`, `tools/inference/validate_context_manifest.py`, `schemas/inference/examples/context_manifest.example.json` (fail-closed upfront contract shipped; `claim_tier` bound to the canonical ladder. Gap: not yet wired as a pre-run gate on the live kernel entry point) |
| WP-02 | L2 microstructure contract | EXISTS | `research/microstructure/BASELINE.L2.md`, `…/attribution.py`, `…/conditional_transfer_entropy.py` |
| WP-03 | Manifold substrate | EXISTS | `core/indicators/market_state_contract.py`, `core/indicators/kuramoto_ricci_composite.py` |
| WP-04 | Ricci curvature field | EXISTS | `core/indicators/ricci.py`, `core/indicators/temporal_ricci.py`, `core/physics/forman_ricci.py`, `core/kuramoto/ricci_flow_engine.py` |
| WP-05 | Kuramoto phase field | EXISTS | `core/kuramoto/kuramoto_ricci_engine.py`, `core/kuramoto/metrics.py` |
| WP-06 | Fused Ricci-Kuramoto kernel | EXISTS | `core/indicators/kuramoto_ricci_composite.py`, `scripts/integrate_kuramoto_ricci.py` |
| WP-07 | Recursive falsification loop | PARTIAL | `tools/inference/recursive_falsification_driver.py` (binds null + claim-ladder into the loop; can refute; capped at MEASURED_SYNTHETIC), `core/kuramoto/oos_validation.py` (walk-forward + Diebold-Mariano + SPA), `analytics/signals/null_baseline.py`, `geosync_hpc/nulls/dynamic_null_model.py`, `docs/research/D002J_NULL_MODEL_CONTRACTS.md`, `docs/research/D002J_NULL_MODEL_HIERARCHY.md` (driver runs on synthetic input; real-data loop pending) |
| WP-08 | Claim-tier promotion governance | EXISTS | `governance/CLAIM_MATURITY.yaml`, `analytics/signals/claim_maturity.py`, `application/governance/claim_ledger.py`, `scripts/ci/check_claim_maturity.py`, `docs/schemas/governance/claim_ledger.schema.json` |
| WP-09 | Machine-verification bundle | PARTIAL | `tools/inference/assemble_evidence_bundle.py`, `manifests/research/release_provenance.v1.json` (assembler shipped: binds a validated manifest + a real null + a ladder-checked claim card into one hashed bundle; refuses an unearned tier. Gap: baseline/OOS/cost are `NOT_RUN` until a validated run fills them) |
| WP-10 | External-rank path | GAP | — (no Zenodo DOI / JOSS draft) |

## The real remaining work (not the whole act)

The act's ten packages reduce to a small set of genuine gaps plus a binding
layer; the rest is already implemented and should be *wired*, not rebuilt.

**Shipped (contract layer):**

- **WP-01** — a fail-closed upfront **context contract** (`context_manifest`
  schema + validator) binding problem / universe / window / data-source SHA /
  target / claim-tier / nulls / stop-rule / evidence-path, with `claim_tier`
  validated against the canonical ladder. *Remaining:* wire it as a pre-run gate
  on the live kernel entry point.
- **WP-09** — a **bundle assembler** that binds a validated manifest + a real
  null + a ladder-checked claim card into one content-hashed bundle and
  **refuses a tier the evidence does not earn**. *Remaining:* baseline / OOS /
  cost slots are `NOT_RUN` until a validated run fills them.

**Open gaps:**

- **WP-07** — an end-to-end **recursive driver** chaining the existing null,
  baseline, OOS and claim-ladder components into one
  `output → claim classifier → null challenge → residual → revised context` loop.
- **WP-10** — the **external-rank** steps (DOI, JOSS, public benchmark table).

These contract pieces are admissibility infrastructure: they make a run
inspectable and a claim un-inflatable. They do **not** move predictive rank —
that still requires a validated run on real L2 data through the existing
null / baseline / OOS components, which neither WP-01 nor WP-09 supplies.

WP-08's existing `evaluate_promotion` ladder (UNOBSERVED → MEASURED with a
null + simpler-baseline + replay + provenance + falsifier + negative-evidence
conjunction, no state-skipping, no synthetic→real promotion) is **stricter** than
the act's WP-08 sketch and is the canonical claim-tier authority. New work
adopts it rather than introducing a second ladder.

## Machine-readable coverage (validated)

<!-- WP-COVERAGE-DATA -->
```json
{
  "schema_version": 1,
  "work_packages": [
    {
      "id": "WP-01",
      "title": "Contextualization frame",
      "status": "PARTIAL",
      "artifacts": [
        "schemas/inference/context_manifest.schema.json",
        "tools/inference/validate_context_manifest.py",
        "schemas/inference/examples/context_manifest.example.json"
      ],
      "gap": "fail-closed upfront context contract shipped (claim_tier bound to the canonical ladder); not yet wired as a pre-run gate on the live kernel entry point"
    },
    {
      "id": "WP-02",
      "title": "L2 microstructure contract",
      "status": "EXISTS",
      "artifacts": [
        "research/microstructure/BASELINE.L2.md",
        "research/microstructure/attribution.py",
        "research/microstructure/conditional_transfer_entropy.py"
      ]
    },
    {
      "id": "WP-03",
      "title": "Manifold substrate",
      "status": "EXISTS",
      "artifacts": [
        "core/indicators/market_state_contract.py",
        "core/indicators/kuramoto_ricci_composite.py"
      ]
    },
    {
      "id": "WP-04",
      "title": "Ricci curvature field",
      "status": "EXISTS",
      "artifacts": [
        "core/indicators/ricci.py",
        "core/indicators/temporal_ricci.py",
        "core/physics/forman_ricci.py",
        "core/kuramoto/ricci_flow_engine.py"
      ]
    },
    {
      "id": "WP-05",
      "title": "Kuramoto phase field",
      "status": "EXISTS",
      "artifacts": [
        "core/kuramoto/kuramoto_ricci_engine.py",
        "core/kuramoto/metrics.py"
      ]
    },
    {
      "id": "WP-06",
      "title": "Fused Ricci-Kuramoto kernel",
      "status": "EXISTS",
      "artifacts": [
        "core/indicators/kuramoto_ricci_composite.py",
        "scripts/integrate_kuramoto_ricci.py"
      ]
    },
    {
      "id": "WP-07",
      "title": "Recursive falsification loop",
      "status": "PARTIAL",
      "artifacts": [
        "tools/inference/recursive_falsification_driver.py",
        "core/kuramoto/oos_validation.py",
        "analytics/signals/null_baseline.py",
        "geosync_hpc/nulls/dynamic_null_model.py",
        "docs/research/D002J_NULL_MODEL_CONTRACTS.md",
        "docs/research/D002J_NULL_MODEL_HIERARCHY.md"
      ],
      "gap": "recursive driver shipped (binds null + claim-ladder, can refute, capped at MEASURED_SYNTHETIC); runs on synthetic input — real-data loop pending"
    },
    {
      "id": "WP-08",
      "title": "Claim-tier promotion governance",
      "status": "EXISTS",
      "artifacts": [
        "governance/CLAIM_MATURITY.yaml",
        "analytics/signals/claim_maturity.py",
        "application/governance/claim_ledger.py",
        "scripts/ci/check_claim_maturity.py",
        "docs/schemas/governance/claim_ledger.schema.json"
      ]
    },
    {
      "id": "WP-09",
      "title": "Machine-verification bundle",
      "status": "PARTIAL",
      "artifacts": [
        "tools/inference/assemble_evidence_bundle.py",
        "manifests/research/release_provenance.v1.json"
      ],
      "gap": "assembler binds a validated manifest + a real null + a ladder-checked claim card into one hashed bundle and refuses an unearned tier; baseline/OOS/cost remain NOT_RUN until a validated run fills them"
    },
    {
      "id": "WP-10",
      "title": "External-rank path",
      "status": "GAP",
      "artifacts": [],
      "gap": "no Zenodo DOI release or JOSS-ready draft"
    }
  ]
}
```
