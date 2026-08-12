# Glossary — semantic-precision definitions

> Scope: this glossary defines, in operational terms, the 20 semantic-
> precision terms required by the canonical documentation quality audit
> protocol (§Semantic Precision Mode). Each entry has: definition,
> in-repo example, evidence path, boundary (when the term is *not*
> appropriate). If a term is used in repo docs without an entry here,
> the audit treats it as UNDEFINED and a defect.
>
> All entries below are bounded by the current 2026-05-05 evidence
> snapshot. Any future term-meaning change must update this file in
> the same commit.

---

## Term: `agent`

* **Definition.** A process or module with explicit input contract,
  explicit output contract, and a stop condition. Not "anything that
  computes".
* **In-repo example.** `runtime/cognitive_bridge/cycle.py` — the 15-stage
  semantic-sieve cycle has typed input (RAW_SIGNAL), typed output
  (KNOWLEDGE_NODE), and a deterministic stop (commit_to_memory or ABORT).
* **Boundary.** The word `agent` MUST NOT be applied to plain functions,
  background tasks without artifact output, or LLM calls that do not
  produce auditable artifacts.

## Term: `anchored`

* **Definition.** A claim is *anchored* when there is a local file,
  test, config, script, or reproducible output that supports it.
* **In-repo example.** `INV-DA7` is anchored to
  `core/neuro/dopamine/dopamine_controller.py::compute_rpe` and the
  property test `test_dpa_td_lambda` (cycle #1 follow-up).
* **Boundary.** A claim with no evidence path is NOT anchored, even if
  it is correct in principle.

## Term: `architecture`

* **Definition.** The decomposition of a system into modules, contracts,
  interfaces, data flow, control flow, memory model, error handling,
  verification gates, observability, failure modes, and test surface.
* **In-repo example.** `docs/ARCHITECTURE.md` (top-level) +
  `physics_contracts/catalog.yaml` (contracts) + `.importlinter`
  (boundaries).
* **Boundary.** The word `architecture` MUST NOT be used for a single
  diagram or a list of features; it requires the full decomposition
  above.

## Term: `benchmark`

* **Definition.** A reproducible experiment with stated inputs, stated
  acceptance criteria, signed output artefact, and a baseline.
* **In-repo example.** `tools/reset_wave_offline_benchmark.py` —
  fixed seed (2026), Monte-Carlo `n=2000`, three reported rates
  (`sync_monotonic_rate`, `async_monotonic_rate`, `async_lock_rate`).
* **Boundary.** A timing measurement without baseline or acceptance
  criterion is NOT a benchmark.

## Term: `cognition`

* **Definition.** Within this repo, "cognition" denotes the 15-stage
  state-machine pipeline in `runtime/cognitive_bridge/cycle.py` —
  nothing more. NOT a claim about consciousness, awareness, or any
  property of biological cognition.
* **Boundary.** Outside that pipeline, the word `cognition` is decorative
  and MUST be replaced by the concrete operation (e.g. "decision",
  "inference", "scoring").

## Term: `consciousness`

* **Definition.** Out of scope for this repository. The repo has no
  module, contract, or measurement that operationalises consciousness.
* **Boundary.** Documentation MUST NOT use the term `consciousness` as
  a description of any module, function, or behaviour. (Status:
  `REJECTED` per audit policy.)

## Term: `criticality`

* **Definition.** Refers strictly to the adaptive-criticality contract
  `INV-AC1-rev` defined in `CLAUDE.md` (κ_critical = -ln(ΔH_max/ε) /
  (λ_local + δ)). Computed in
  `geosync/estimators/dfa_gamma_estimator.py::hurst_exponent`.
* **Boundary.** Generic phrases such as "the system is critical" without
  reference to `INV-AC1-rev` or to a measurable κ are decorative and
  MUST be removed or scoped.

## Term: `evidence`

* **Definition.** A local file (test, config, signed JSON, manifest, or
  artefact) that supports a claim and can be re-verified by an
  external reviewer with the repository alone.
* **In-repo example.** `docs/PERFORMANCE_LEDGER.md` rows must point at a
  `results/*.json` artefact for every measured number; that pointer is
  the evidence.
* **Boundary.** A claim "validated by extensive testing" without naming
  which test gives no evidence.

## Term: `falsification`

* **Definition.** A specific empirical condition under which a claim
  would be rejected. Required for every strong claim per `CLAIMS.md`.
* **In-repo example.** `INV-K2` falsification:
  `R > 3/√N after 10⁴ steps with K = 0.1·K_c and N > 100`.
* **Boundary.** Statements like "we tested it thoroughly" are NOT
  falsifications. A real falsification names the input, the threshold,
  the duration, and the negative outcome.

## Term: `framework`

* **Definition.** Within this repo, `framework` is reserved for the
  overall GeoSync platform. Not used for individual modules.
* **Boundary.** A single `.py` file or a small package MUST NOT be
  called a `framework`.

## Term: `intelligence`

* **Definition.** Out of scope. The repo does not operationalise the
  word `intelligence`. The closest formal proxy is the EFE arbitration
  pathway (Friston 2010) currently scoped under
  `geosync/neuroeconomics/epistemic_action.py`.
* **Boundary.** Documentation MUST NOT claim "intelligence" as a
  property of any module. Status: `REJECTED` for use in surface docs.

## Term: `invariant`

* **Definition.** A machine-checkable predicate registered in
  `.claude/physics/INVARIANTS.yaml` with a `falsification`
  field and at least one binding test under `tests/`.
* **In-repo example.** `INV-K1` (0 ≤ R(t) ≤ 1) is registered with type
  `universal`, priority `P0`, and falsifier
  `R > 1.0 ∨ R < 0 at any t`.
* **Boundary.** A predicate stated in prose without registry presence
  is NOT an invariant — it is at most a hypothesis.

## Term: `kernel`

* **Definition.** The set of contracts and tests in
  `.claude/physics/INVARIANTS.yaml` plus `physics_contracts/catalog.yaml`,
  loaded as a precondition for every CI run via the `physics-gate`
  workflow.
* **Boundary.** "Kernel" MUST NOT be used as a synonym for "core" or
  "engine".

## Term: `metastability`

* **Definition.** A regime label produced by `core/dro_ara/engine.py`
  when `regime ∈ {METASTABLE, …}` per `INV-DRO3`. Defined operationally
  by Hurst-exponent / γ relations, not as a literary metaphor.
* **Boundary.** "Metastable" MUST NOT be used outside the DRO-ARA
  regime axis without explicit referencing.

## Term: `pipeline`

* **Definition.** A composed sequence of stages with typed inputs and
  outputs and a deterministic terminator.
* **In-repo example.** `runtime/cognitive_bridge/cycle.py` — 15-stage
  pipeline with `commit_to_memory` as the only terminal.
* **Boundary.** A list of function calls without typed contract is NOT
  a pipeline.

## Term: `production`

* **Definition.** Within this repo, "production" means **module-level
  production-scoped** unless explicitly qualified by L-1 in
  `docs/KNOWN_LIMITATIONS.md`. Live-venue trading is NOT in scope of
  the current 2026-05-05 snapshot.
* **Boundary.** "Production-ready" used without qualifier in
  customer-facing docs is a defect (per Pass-1+Pass-2 audit catalog).

## Term: `substrate`

* **Definition.** Bounded use only: the `.claude/physics/` kernel and
  the `physics_contracts/catalog.yaml` file together form the *physics
  substrate* of the platform — the contracts that all other modules
  must respect.
* **Boundary.** The word MUST NOT be applied to abstract concepts like
  "intelligence substrate" without an explicit registry pointer.

## Term: `system`

* **Definition.** A composition of modules with declared boundaries,
  contracts (`.importlinter` + `physics_contracts/catalog.yaml`),
  observability surface, and an end-to-end test surface (`tests/`).
* **Boundary.** "System" MUST NOT be used loosely as a stand-in for
  "code".

## Term: `validation`

* **Definition.** Successful execution of a named test or evidence
  protocol against a stated input — with the test name cited.
* **In-repo example.** "DRO-ARA regime gating is validated by
  `tests/unit/physics/test_DRO*` (INV-DRO1..5)" — citation makes it
  validation, not just a claim.
* **Boundary.** "Validated by extensive testing" with no test name is
  NOT validation; it is a hypothesis.

## Term: `verification`

* **Definition.** Mechanised proof that a property holds across the
  declared input space. Stronger than `validation` (one test) — implies
  property-based, fuzz, or formal coverage.
* **In-repo example.** `tests/test_reset_wave_property_based.py` —
  Hypothesis-generated 800 cases covering monotonicity, lock semantics,
  and manifold closure.
* **Boundary.** A single example test is NOT verification; it is
  validation.

---

## Audit-protocol use

Whenever the audit protocol grep flags a term that is not in this
glossary, treat the use as undefined and either:

1. add an entry here (with evidence path), or
2. replace the term in the doc with concrete observable behaviour, or
3. remove the term.

Last reviewed: 2026-05-05 (canonical-2026-05-05 / commit `95e22e2`).
