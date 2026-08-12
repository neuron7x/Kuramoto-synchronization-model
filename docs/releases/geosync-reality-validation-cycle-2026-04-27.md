# GeoSync Reality-Validation Cycle — 2026-04-27

**Status:** Closed.
**Main SHA at close:** `406dd25`.
**Cycle scope:** PRs #445 → #473 (29 PRs).
**Cycle motto:** *Жодна брехня не стала фактом без бою.*

---

## What this is

A **canonical-state ledger** for the calibration cycle that ran 2026-04-26 →
2026-04-27. It records the historical point at which GeoSync transitioned
from advisory CI to a closed reality-validation loop. It is not a release
notes file in the marketing sense — it is a *commitment that the state
described below is the state we will defend*.

The cycle's structural achievement, in one line:

> ```
> claim → evidence → witness → falsifier → restore → CI gate → regression lock.
> ```

---

## Headline mode shifts

| Before | After |
|---|---|
| advisory CI noise | fail-closed regression detector |
| pattern PROPOSED | pattern IMPLEMENTED with mutation-killed tests |
| "tests pass locally" | conftest deps installed in CI; CI is honest |
| 71 historical findings shrugged off as advisory | 71 findings on a manifest, each with a per-class reason; new findings trip the gate |
| `physical equivalence` / `predicts returns` rejected only in source pack | same red-line set rejected in translation matrix too |

Repository transitioned from *"we know there are problems here"* to *"a new
lie does not pass without a mechanical witness"*.

---

## Merged PRs grouped by named lie blocked

### Foundation: dependency / coverage / security honesty

| PR | Lie blocked |
|---|---|
| #445 | "range drift = active install" / "vulnerable lock = exploit" |
| #447 | "ledger entry = evidence" (claim ledger + evidence weight matrix) |
| #448 | calibration tasks 3/4/6/7/8/9 (false-confidence detector, reachability graph, mutation kill ledger, architecture boundaries, dependency truth unifier, system truth report) |
| #449 | "physics analogy = engineering equivalence" (physics-2026 evidence rail with validators) |
| #451 | "coverage number = real coverage" (F02 closure; .coveragerc honesty) |
| #452 | "version safe = reachability resolved" (F03 reachability witness for GraphQL WS, closes #446) |
| #453 | "manifests reproducible while make lock fails" (D7 detector + lock-regeneration fix) |

### Physics-2026 patterns P1 → P10 (engineering analogs only)

| PR | Lie blocked |
|---|---|
| #450 | "cataloged event = prediction" (P1 PopulationEventCatalog) |
| #463 | "missing data = true absence" (P2 StructuredAbsence) |
| #455 | "baseline fixed forever" (P3 DynamicNullModel) + "local pass = global pass" (P4 GlobalParityWitness) |
| #461 | "static correlation = dynamic relation" (P5 MotionalCorrelationWitness) + "correlation = binding" (P6 CompositeBindingStructure) |
| #464 | "new physics idea = validated GeoSync instrument" (S7-S10 sources + P7-P10 patterns added at PROPOSED only) |
| #465 | "regime transitions are smooth unless proven otherwise" (P7 RegimeFrontRoughness) |
| #466 | "longer reasoning chain = deeper truth" (P9 EffectiveDepthGuard) |
| #470 | "one growth exponent explains all windows" (P8 NonSelfSimilarClusterGrowth) |
| #471 | "a single local check is a global proof" (P10 ClaimGaugeWitness) |

### System composition + CI wiring

| PR | Lie blocked |
|---|---|
| #462 | "individual witnesses pass = system claim valid" (reality-chain integration test) + "validators exist = enforce" (physics-2026-gate.yml) |
| #467 | extends the chain to optionally cover P7 + P9 |
| #468 | "validators exist = validators enforce" (reality-validators-gate.yml: claims/evidence/dep-truth fail-closed; injection-probe) |
| #469 | "CI failure is harmless because local validation passed" (physics-2026-gate.yml dependency bootstrap fix) |
| #472 | "advisory CI = silent acceptance of historical state" (false-confidence exemption manifest; regression detector) |
| #473 | "advisory CI cannot tell historical state from regression" (flips false-confidence to fail-closed) |

---

## P1 → P10 implementation table

All ten patterns are at `claim_tier: ENGINEERING_ANALOG`,
`implementation_status: IMPLEMENTED`. None claim physical equivalence.
None emit forecasts, signals, or recommendations.

| Pattern | Source | Module | Lie blocked | Falsifier (mutation candidate) |
|---|---|---|---|---|
| P1 | S1 GWTC-4 | `geosync_hpc/regimes/population_event_catalog.py` | "cataloged event = prediction" | negate duplicate-rejection branch |
| P2 | S2 PI-gap | `geosync_hpc/regimes/structured_absence.py` | "missing data = true absence" | invert bias-precedence branch |
| P3 | S3 DESI 2026 | `geosync_hpc/nulls/dynamic_null_model.py` | "baseline fixed forever" | invert drift-bound check |
| P4 | S4 Kitaev | `geosync_hpc/coherence/global_parity_witness.py` | "local pass = global pass" | ignore dependency_truth_ok=False |
| P5 | S5 helium-Bell | `geosync_hpc/dynamics/motional_correlation_witness.py` | "static corr = dynamic relation" | drop shuffled-null comparison |
| P6 | S6 LHCb baryon | `geosync_hpc/coherence/composite_binding_structure.py` | "correlation = binding" | drop perturbation-response check |
| P7 | S7 KPZ 2D | `geosync_hpc/regimes/regime_front_roughness_witness.py` | "transitions are smooth by default" | drop shuffled-null comparison |
| P8 | S8 active-coarsening | `geosync_hpc/regimes/non_selfsimilar_cluster_growth.py` | "one exponent explains all windows" | replace per-window check with global fit |
| P9 | S9 noise-shallow | `geosync_hpc/inference/effective_depth_guard.py` | "longer reasoning = deeper truth" | drop equivalence-tolerance check |
| P10 | S10 logical-gauging | `geosync_hpc/coherence/claim_gauge_witness.py` | "single local check = global proof" | skip required-constraints intersection |

Reality chain (`tests/integration/test_physics_2026_reality_chain.py`)
composes P1..P6 mandatorily and P7 + P9 optionally. Boolean AND only —
no numeric system-health score.

---

## CI gates now fail-closed

| Workflow | Job | Mode |
|---|---|---|
| `physics-2026-gate.yml` | physics-2026-validators | fail-closed (sources + translation validators) |
| `physics-2026-gate.yml` | physics-2026-unit-tests | fail-closed (P1..P6 + research) |
| `physics-2026-gate.yml` | physics-2026-integration-chain | fail-closed (P1..P6 reality chain) |
| `physics-2026-gate.yml` | physics-2026-injection-probe | fail-closed (forbidden-overclaim mutation rejected) |
| `reality-validators-gate.yml` | reality-claim-ledger | fail-closed |
| `reality-validators-gate.yml` | reality-evidence-matrix | fail-closed |
| `reality-validators-gate.yml` | reality-dependency-truth | fail-closed |
| `reality-validators-gate.yml` | reality-false-confidence-regression | **fail-closed (#473)** — was advisory before #472 |
| `reality-validators-gate.yml` | reality-validators-injection-probe | fail-closed |

The validators in `tools/research/`, `.claude/claims/`, `.claude/evidence/`,
`tools/deps/`, `tools/audit/` are now *required* on every PR that touches
their input paths.

---

## Falsifier summary — every PR proved its lie was blocked

For each PR landed in this cycle, a deliberate mutation was applied that
re-introduces the named lie, the test suite was re-run, the targeted tests
*failed* under the mutation, then the source was restored from a `/tmp/`
backup and the suite passed again.

Probe locations and outcomes are in each merge commit body (ledger of
mutation, expected failures, restore evidence). A single representative
sample:

- **#472** (manifest mechanism): removed one `C10-BROAD-EXCEPTION-...`
  entry from `.claude/audit/false_confidence_exemptions.yaml`. Detector
  emitted that exact finding (`1 finding`). Restored manifest from
  `/tmp/_probe_manifest.bak`. Detector emitted `0 findings`.
- **#473** (advisory → fail-closed): wrote
  `_falsifier_probe_new_c10.py` with 6 `except Exception:` blocks.
  Detector exited `1` (regression caught; not on manifest). Removed
  probe. Detector exited `0`.
- **#469** (CI bootstrap): stubbed `pandas` to raise
  `ModuleNotFoundError`; pytest collection failed *identically* to the
  observed CI failure. Pandas restored; collection clean.

The pattern repeats across all 29 cycle PRs.

---

## Documented baseline — `.claude/audit/false_confidence_exemptions.yaml`

71 historical findings are recorded in the manifest, each with a
per-class reason. The detector is now a **regression detector**:

- `C2` × 3 — Docker scanner-path mismatch on `coherence_bridge`,
  `cortex_service`, `sandbox` Dockerfiles.
- `C3` × 11 — test-name overclaim audited for type-narrowing /
  boundary-input contexts.
- `C6` × 1 — synthetic pointer to dependency-truth (cleared by D6/D7).
- `C8` × 11 — `# type: ignore` concentration rooted in third-party stub
  gaps (pandas / strawberry / prometheus / sqlalchemy).
- `C9` × 20 — `# pragma: no cover` on platform-specific or
  environment-conditional branches.
- `C10` × 25 — `except Exception:` concentration on sandbox boundaries,
  plugin loaders, runtime telemetry, and CLI top-level handlers where
  broad catch is the documented contract.

Reducing these 71 to zero by *real refactor* is a future cycle — out of
scope for this canonical-state lock-in. The manifest exists so that any
*new* concentration must be defended on its own merits (or admitted as
historical state on its own).

---

## Remaining known limitations

These are explicit non-claims of this cycle:

1. **No "production-ready" or "fully verified" claim.** The witnesses
   block named lies; they do not certify global system correctness.
2. **`lint-imports` not yet wired** into `reality-validators-gate.yml`
   (header still flags it as advisory pending the import-linter
   configuration).
3. **The 71 baseline findings remain in code.** They are documented, not
   fixed. Real refactor is a future cycle.
4. **Reality chain covers P1..P6 mandatorily and P7/P9 optionally.** P8
   and P10 are not yet wired into the chain (each is fully validated
   standalone via its own falsifier, but their composition into the
   system-claim AND is a follow-up).
5. **No new lint-imports / deptry / property-based fuzzing of validator
   bodies in CI.** The injection-probe job tests one mutation per
   workflow run, not a fuzz-set.
6. **Forbidden-phrase scan is case-insensitive substring.** Obfuscated
   paraphrases (e.g. `"law of physics, new"`) would slip through. A
   tokenized / lemmatized scan is a separate research task.

---

## Next non-urgent roadmap

In priority order, with no commitment to dates:

1. **Wire `lint-imports`** into `reality-validators-gate.yml` after
   adopting an `.importlinter` config; falsifier: introduce a
   forbidden import → CI fails.
2. **Reduce the 71-finding baseline by real refactor**, one class at a
   time. C2 (3 entries) and C6 (1 entry) are closest to clean. Each
   clean class shrinks the manifest; the manifest never grows.
3. **Extend reality chain to wire P8 and P10** as optional gates,
   matching the P7/P9 pattern from #467.
4. **Replace forbidden-phrase substring scan with a token-aware
   matcher** so paraphrases cannot smuggle red-line claims.
5. **Add deptry-driven D6 detector** to `tools/deps/` so direct-imports-
   of-transitive-deps are first-class, not synthetic-pointer C6 noise.
6. **Tighten `physics-2026-gate.yml` install lists** to use
   `requirements-scan.txt` (canonical lean-install path) rather than
   minimal pinned set; falsifier: remove a transitively-required dep
   from `requirements-scan.txt` → conftest collection fails.

None of these are blocking. The canonical state is closed.

---

## Closure

```
GeoSync now has a closed reality-validation loop:
claim → evidence → witness → falsifier → restore → CI gate → regression lock.
```

Anything that contradicts this document either represents a regression
(fix it) or a deliberate evolution (open a PR with a falsifier proving
the new claim survives the same audit).

— *2026-04-27*
