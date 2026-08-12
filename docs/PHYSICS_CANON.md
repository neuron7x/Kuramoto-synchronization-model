# GeoSync Physics Canon

> **Status:** canonical. This is the single reviewer-facing entry point for the
> GeoSync physics layer. It is machine-checked by
> `scripts/ci/check_physics_docs_canon.py` against the law catalog
> (`physics_contracts/catalog.yaml`), the invariant registry
> (`.claude/physics/INVARIANTS.yaml`), and the binding manifest
> (`docs/PHYSICS_CANON.manifest.json`). Audit reports under `docs/audit/` are
> historical evidence, **not** the specification — start here, not there.

---

## 1. Scope

The GeoSync physics layer is a **verification-oriented computational-physics
contract layer** for falsifiable market-structure research hypotheses. It
formalizes synchronization, graph curvature, energy-like constraints, and
evidence-bound invariants as **executable checks** over the system's own
computation.

It binds **42 laws** and **132 invariants** into seven classified domains. Every
law and every invariant is assigned to exactly one domain in
`docs/PHYSICS_CANON.manifest.json`; the gate fails closed if any law or
invariant is unclassified, double-counted, or drifts from the substrates.

## 2. Non-claims

This layer does **not** prove that markets obey any physical law. It does **not**
assert alpha, prediction, profitability, rank, or deployment readiness. The
canonical product boundary is `PRODUCT_CATEGORY.md`; the enforced phrase
firewall is `FORBIDDEN_CLAIMS.md`. Each banned framing below is asserted **never**:

- No validated alpha and no proven predictor of price or returns.
- No guaranteed edge and no deployable strategy.
- No law of markets and never market physics proven on data.

What the layer *does* prove are **invariants of its own computation** — that the
code respects the mathematics it implements, within stated validity domains.

## 3. Domain taxonomy

Each domain carries a **kind** and a **maturity**. A domain may never be
presented at a maturity above its evidence. The full per-id membership lives in
the manifest; the table below is the human summary.

| Domain | Kind | Maturity | Laws | Inv. |
|---|---|---|---:|---:|
| `graph_geometry` | physics law | `FORMAL_LAW` | 5 | 5 |
| `nonlinear_synchronization` | physics law | `FORMAL_LAW` | 5 | 40 |
| `computational_physics_contract` | derived property | `DERIVED_COMPUTATIONAL_PROPERTY` | 4 | 14 |
| `market_microstructure_hypothesis` | research hypothesis | `HYPOTHESIS` | 9 | 7 |
| `neuro_symbolic_analogy` | non-claim analogy | `NON_CLAIM_ANALOGY` | 6 | 29 |
| `execution_infrastructure` | execution contract | `INVARIANT` | 10 | 25 |
| `personal_research_ontology` | research ontology | `NON_CLAIM_ANALOGY` | 3 | 12 |

**Classification rules (enforced):**

- `neuro_symbolic_analogy` and `personal_research_ontology` are **not** physics
  of markets. Serotonin / dopamine / GABA / cryptobiosis / homeostatic dynamics
  are engineering analogies; their biological labels are arithmetic proxies. The
  gradient-ontology axiom (`INV-YV1`) and the PNCC cosmological-compute axioms
  are the author's research framing, scoped to the system's substrate.
- `market_microstructure_hypothesis` items are research hypotheses; they cannot
  be promoted without real-data evidence (hashes, seed, null baseline).
- `graph_geometry` and `nonlinear_synchronization` are formal mathematical
  results that hold **only inside their stated validity domain**.

## 4. Law catalog

The 42 laws live in `physics_contracts/catalog.yaml`. Each law object carries
`id`, `module`, `statement`, `formula`, `variables`, `tolerance`, `validity`,
`source`, `severity`. Tolerances in witness tests must derive from a law's
formula, never from magic literals. The canonical per-domain membership is the
`domains.<domain>.laws` list of the manifest.

Representative laws by domain:

- `graph_geometry`: `ricci.ollivier_bounds`, `ricci.gauss_bonnet`, `kuramoto_ricci.semantics_split`
- `nonlinear_synchronization`: `kuramoto.order_parameter_bounds`, `kuramoto.critical_scaling`
- `computational_physics_contract`: `thermo.second_law_closed`, `thermo.landauer_bound`, `ecs.lyapunov_descent`
- `market_microstructure_hypothesis`: `dro_ara.gamma_derivation`, `manifold.causal_cutoff`
- `neuro_symbolic_analogy`: `serotonin.level_bounds`, `dopamine.bounded_signal`, `gaba.gate_bounds`
- `execution_infrastructure`: `kelly.optimal_fraction_formula`, `oms.idempotency`, `hpc.seeded_reproducibility`
- `personal_research_ontology`: `pncc.landauer_proxy_dominance`, `pncc.no_bio_claim`

## 5. Invariant registry

The 132 invariants live in `.claude/physics/INVARIANTS.yaml`, organized by
section, and are counted canonically by `python scripts/count_invariants.py`
(must read `132`). The header in `CLAUDE.md`, the README badge, and `BASELINE.md`
mirror that count; the `invariant-count-sync` gate fails closed on divergence.
The canonical per-domain membership is the `domains.<domain>.invariants` list of
the manifest.

Each invariant has a type (`universal`, `asymptotic`, `monotonic`,
`statistical`, `algebraic`, `qualitative`, `conservation`), a falsification
criterion, a `source`, and `tests`. Severity tiers: `P0` (block), `P1`, `P2`.

## 6. Evidence lifecycle

The claim-promotion automaton (`docs/REPOSITORY_SYSTEM.md`) governs how a
statement earns standing:

```
IDEA → HYPOTHESIS → PREREGISTERED → INSTRUMENTED
     → TESTED_SYNTHETIC → TESTED_REAL_SINGLE → TESTED_REAL_MULTI
     → MEASURED → REPLICATED
```

Allowed evidence statuses (from `FORBIDDEN_CLAIMS.md`): `Active`,
`Not Measured`, `Not Deployable`, `Instrumented`, `Measured-Single`,
`Measured-Multi`, `Blocked`. Synthetic data can reach at most `Instrumented`. A
real-data artifact must pass schema, null, and falsifier gates before it can
advance, and must carry data/config hashes for replay.

## 7. Falsification lifecycle

Every claim binds a falsifier — a command or test that returns non-zero when the
claim is broken. The chain is: `claim → invariant → data source → method →
artifact → falsifier → replay path`. A claim with no falsifier cannot be
promoted (ADR `docs/adr/0021-falsifier-required-anchored-claims.md`). Witness
tests are mathematical witnesses: they fail if the code stops respecting the law.

## 8. Current maturity

The per-domain maturity is fixed in the manifest and summarized in §3. The
detailed domain → status → evidence-tier → allowed/forbidden mapping is
`docs/PHYSICS_MATURITY_MATRIX.md`. No domain may imply a maturity above its
evidence tier; the maturity vocabulary is closed to: `FORMAL_LAW`, `INVARIANT`,
`DERIVED_COMPUTATIONAL_PROPERTY`, `HYPOTHESIS`, `NON_CLAIM_ANALOGY`.

## 9. Known gaps

- `market_microstructure_hypothesis` domains remain at `HYPOTHESIS`: no
  multi-session real-data promotion is asserted (e.g. the Ricci microstructure
  lane — see `docs/research/RICCI_MICROSTRUCTURE_STATUS.md`).
- Two `manifold.*` laws are `DRAFT` in the catalog (`validity` marked DRAFT) and
  are carried as hypotheses, not formal laws.
- `physics_contracts` is shipped as a standalone namespace and is **not** in the
  wheel's `packages.find` include list; physics verification therefore requires
  the runbook's environment setup (`docs/PHYSICS_VERIFICATION_RUNBOOK.md`).

## 10. Verification commands

The exact environment and command set is `docs/PHYSICS_VERIFICATION_RUNBOOK.md`.
The canon-specific gate is:

```bash
python scripts/ci/check_physics_docs_canon.py          # verify manifest + canon docs
python scripts/ci/check_physics_docs_canon.py --write  # regenerate the manifest
```

Supporting gates: `check_claim_boundary.py`, `check_docs_consistency.py`,
`check_invariant_source_binding.py`, `check_physics_law_witness_index.py`,
`check_physics_inference_readiness.py`, and `python scripts/count_invariants.py`.
