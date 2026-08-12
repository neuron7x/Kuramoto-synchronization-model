# Neuro-Physics Contradiction Ledger (Assurance-Case v2)

Machine-readable source of truth: [`data/audit/neuro_physics_contradiction_ledger.json`](../../data/audit/neuro_physics_contradiction_ledger.json)
validated against [`schemas/audit/contradiction_ledger.schema.json`](../../schemas/audit/contradiction_ledger.schema.json)
by `tests/audit/test_contradiction_ledger.py`.

## Methodology

This ledger is a **continuously-verifiable assurance case**, not a flat list. It
adopts three established academic standards so that every claim is *defended* and
*machine-checked*, not merely asserted:

- **Toulmin argument model** (Toulmin, *The Uses of Argument*, Cambridge UP, 1958/2003).
  Each contradiction carries `grounds` (source path + line evidence) →
  `warrant` (the inference rule) → `backing` (the authority: an invariant id, a
  canonical doc, or a peer-reviewed source) → `qualifier` (`severity` +
  `claim_status`) → `rebuttal` (the condition that would overturn the verdict).
- **W3C-PROV provenance**. Each entry records `asserted_by` / `asserted_on` /
  `method` — who made the claim, when, and how it was verified.
- **Executable falsifier per claim** (cf. Goal Structuring Notation assurance
  cases; Kelly & Weaver 2004). Each entry ships a shell `falsifier.command`
  authored to **exit 0 IFF the entry's stated position is still true against live
  source**. CI executes every falsifier
  (`test_every_falsifier_confirms_its_claim_against_live_source`). When a later
  code change invalidates an entry — the dead invariant gets wired, a metaphor
  gets renamed, a resolution lands or regresses — its falsifier stops returning 0
  and CI fails, **forcing a ledger update rather than silent staleness**.

## Law

> No neuro or physics claim exists without grounds (source + evidence), a warrant,
> a backing authority, a rebuttal condition, provenance, and an executable
> falsifier. A claim without evidence is `UNSUPPORTED` — never silently passed.
> Closure requires a `resolution_ref` (no fake closure) **and** a falsifier that
> proves the resolution landed on disk.

`claim_status ∈ {VERIFIED, PLAUSIBLE, UNSUPPORTED, CONTRADICTED}` ·
`severity ∈ {HIGH, MEDIUM, LOW}` ·
`resolution_state ∈ {OPEN, IN_PROGRESS, RESOLVED, WONTFIX}`.

## Ledger

Verified against real source on 2026-06-17. The remediation program anticipated
many contradictions; most are **already bounded** by the repo's own canon. Only
**C-ENERGY-001** was a true HIGH violation (now **RESOLVED** via #1146 + #1149)
and **C-NEURO-003** was a genuinely-actionable MEDIUM, now **RESOLVED** (#1180):
the declared dopamine/serotonin correlation invariant is enforced in
`validate_*` and its falsifier matches live source. The rest are LOW
(naming nits), `UNSUPPORTED` (mechanism already exists), or bounded at the
documentation layer.

| id | severity | status | source | owner lane | resolution |
|----|----------|--------|--------|------------|------------|
| **C-ENERGY-001** | HIGH | CONTRADICTED | `core/energy.py` | lane-2-energy-contract | RESOLVED (#1146,#1149) |
| **C-NEURO-003** | MEDIUM | CONTRADICTED | `core/validation/neuro_integrity.py:412` | lane-3-neuromodulator-semantics | RESOLVED (#1180) |
| **C-NEURO-001** | LOW | CONTRADICTED | `core/neuro/serotonin_ode.py:118` | lane-3-neuromodulator-semantics | OPEN |
| **C-NEURO-002** | LOW | PLAUSIBLE | `core/neuro/gaba_position_gate.py:102` | lane-3-neuromodulator-semantics | OPEN |
| **C-TACL-001** | LOW | UNSUPPORTED | `core/neuro/ecs_regulator.py:380` | lane-4-tacl-delta-f | WONTFIX |
| **C-KURAMOTO-001** | LOW | PLAUSIBLE | `core/kuramoto/capital_weighted.py:7` | lane-5-kuramoto-ricci-structure | OPEN |
| **C-ORCH-001** | LOW | UNSUPPORTED | `core/agent/orchestrator.py` | lane-6-orchestrator-boundary | WONTFIX |

## Scorecard (lane-7-neuro-physics-scorecard)

Derived mechanically from the ledger; see `claim_status` / `resolution_state`.

| metric | value |
|--------|-------|
| total contradictions tracked | 7 |
| VERIFIED-HIGH open | **0** |
| CONTRADICTED | 3 (2 resolved, 1 open) |
| PLAUSIBLE | 2 |
| UNSUPPORTED | 2 |
| RESOLVED | 2 (C-ENERGY-001, C-NEURO-003) |
| WONTFIX (anticipated-but-unsupported) | 2 |
| OPEN / IN_PROGRESS | 3 |
| dead invariants still open | **0** |
| every claim has executable falsifier | yes (7/7 exit 0 in CI) |

**Verdict: `PARTIAL`.** Both actionable physics contradictions are closed and
falsifier-proven: the HIGH energy-contract violation (C-ENERGY-001) and the
MEDIUM dead-invariant (C-NEURO-003). Both load-bearing gates are now met —
`no VERIFIED-HIGH open` **and** `dead invariants = 0`. The program is still not
`PASS` only because three LOW naming/comment nits remain OPEN as bounded
metaphors (no severity, no enforcement gap). No overclaim: this verdict is
computed from the ledger, not asserted.

## Entries

### C-ENERGY-001 — free energy fused with operational cost (HIGH → RESOLVED)
`system_free_energy()` summed a Boltzmann-scaled term with operational/DevOps
costs and added entropy as a *penalty* under the name "free energy", colliding
with canon `F = U − T·S` (INV-FE2) where entropy *lowers* F. **Resolved** by
separating `operational_cost_energy` (cost functional) from `thermo_free_energy`
(`U − T·S`) with an `ENERGY_UNITS="dimensionless"` unit contract (#1146, repaired
by #1149). Falsifier proves the separation is present on disk.

### C-NEURO-003 — declared correlation invariant is never checked (MEDIUM, the real gap)
`core/validation/neuro_integrity.py:146` declares
`dopamine_serotonin_correlation_min = -0.8` as a "Minimum inverse correlation
expectation", but no `validate_*` path references it — a declared integrity
invariant with no witness (dead invariant), even though `compute_pathway_correlation()`
already exists. **Owner:** Lane 3 (wire a trajectory-correlation check or drop the
field). Falsifier: field mentions ≤ 2 ⇒ still dead.

### C-NEURO-001 — `[0,1]` clamp comment labelled "biological plausibility" (LOW)
A scalar clamp to `[0,1]` is a normalisation choice, not biophysical evidence.
Comment-level overclaim; the dynamics are bio-inspired bounded heuristics.
**Owner:** Lane 3 (reword comment).

### C-NEURO-002 — "STDP-like" label in one metaphor module (LOW, PLAUSIBLE)
`gaba_position_gate` calls RPE-sign weight adaptation "STDP-like" with no
spike-timing relation. **Real STDP already exists** in
`modules/gaba_inhibition_gate.py` (`stdp_tau_plus_ms=16.8`), so the only
actionable scope is renaming the metaphor in the former — not a missing
mechanism. **Owner:** Lane 3.

### C-TACL-001 — ΔF gate ALREADY implemented (LOW, UNSUPPORTED → WONTFIX)
The anticipated "monotonic descent without a ΔF gate" is **not supported**:
`ecs_regulator._enforce_strict_monotonic_descent(new_fe, previous_fe)` +
`core.energy.delta_free_energy(F_prev, F_now, dt)` + INV-FE1/FE3 already enforce
`ΔF ≤ 0`. No remediation PR is warranted.

### C-KURAMOTO-001 — structure-vs-alpha bounded by product canon (LOW, PLAUSIBLE)
The no-alpha boundary is in a module docstring and reinforced by
`PRODUCT_CATEGORY.md` ("research instrumentation, not a promise of live-venue
trading"). Bounded at the documentation layer; an executable repo-wide
`R_is_structure_not_alpha` invariant is optional hardening. **Owner:** Lane 5.

### C-ORCH-001 — orchestrator-as-controller claim absent (LOW, UNSUPPORTED → WONTFIX)
A grep of `core/agent/orchestrator.py` and `core/orchestrator/` finds no
"basal ganglia" / "neural controller" assertion. The anticipated overclaim is
**not evidenced**; Lane 6 is preventive only.

## Maintenance

This ledger is self-verifying and point-in-time. When a lane lands, set the
entry's `resolution_state` to `RESOLVED`, add the merged `resolution_ref`, **and**
update its `falsifier.command` to prove the resolution is on disk — the schema and
`tests/audit/test_contradiction_ledger.py` reject `RESOLVED` without a ref and
execute every falsifier (no fake closure, no silent staleness). The advisory
fake-closure scanner (`tools/governance/check_fake_closure_claims.py`, PR #1145)
enforces the same law on PR bodies.
