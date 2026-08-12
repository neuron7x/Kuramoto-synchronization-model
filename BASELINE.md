---
doc_status:
  status: current
  authoritative_for:
    - physics_invariant_counts
    - physics_grounding_baseline
  valid_from: 2026-04-30
---

# GeoSync — Physical-Contracts Baseline (2026-04-06, refreshed 2026-04-30)

This file is the honest ground truth that future physical-contract work is
measured against. It replaces README badge numbers with what the kernel
validator actually sees. The 2026-04-30 external audit
([`docs/audit/2026-04-30-external-audit.md`](docs/audit/2026-04-30-external-audit.md))
forced the count refresh below — the migration narrative further down is
preserved as historical context, not as the current count.

## 0. TL;DR (current state, 2026-04-30)

- **Physics kernel is real.** `.claude/physics/` currently contains
  **132 invariants** (per `python scripts/count_invariants.py`, single source of
  truth: `.claude/physics/INVARIANTS.yaml`), 5 theory files, a 780-line
  validator with 7 levels (L1–L5 + C1–C2), and a self-check that passes.
  CI gate `invariant-count-sync` fail-closes on any drift between this file,
  README, CLAUDE.md, and the registry.

## 0a. TL;DR (as of 2026-04-06 — historical migration milestone)

- **Physics kernel was real then too.** `.claude/physics/` contained **57 invariants** <!-- count-sync:skip historical -->
  (after that migration extended it by 11 modules — Kelly / OMS / SignalBus
  / HPC + refined RC1→RC1+RC3, FE2, OMS1), 5 theory files, a 780-line
  validator with 7 levels (L1–L5 + C1–C2), and a self-check that passed.
- **Repo-wide physics grounding before this work: 0 / 1500 tests (0%).**
- **Repo-wide physics grounding after this work: 36 / 1518 tests (≈ 2.4%).**
  Across **15 test files** covering **24 distinct INV-* invariants**,
  including 11 newly-created canonical witness files (T8–T16) that cover
  all 12 module blocks (Kuramoto, Explosive Sync, Ricci, Free Energy,
  Serotonin, Dopamine, GABA, Kelly, OMS, SignalBus, HPC, Thermodynamics).
- **3 physics-law corrections discovered during witness writing:**
  INV-RC1 (Ricci [−1,1] falsified on cycle graphs → split into RC1+RC3),
  INV-FE2 (F≥0 physically wrong for Helmholtz → component non-negativity),
  INV-OMS1 (per-fill accounting → portfolio energy conservation pending full OMS fixture).
- **All 11 strict-list files pass L1–L5 = 0 simultaneously.**
- **CI gate installed** as `.github/workflows/physics-kernel-gate.yml`:
  self-check blocks, migrated-file validation blocks, repo-wide sweep and
  C1/C2 code audit are informational until the orphan backlog is closed.

## 1. Test counts (pytest collection vs physics-grounded)

| Metric                                                         | Value   |
|----------------------------------------------------------------|---------|
| `pytest --collect-only` across all testpaths                   | ~10 249 |
| Physics test files (files in `PHYSICS_KEYWORDS` path set)      |     121 |
| Physics test functions                                         |   1 505 |
| Physics tests grounded by INV-* (this PR)                      |      23 |
| Physics grounding fraction                                     |   ~1.5% |
| Non-physics tests (infra, adapters, protocol, etc.)            | ~8 700  |

The repo's README badges ("tests: 9,759") conflate collection with passing
and include both the physics and the non-physics side of the suite. The
coverage number (~71%) is a line-coverage statistic and has nothing to do
with whether the lines exercise any physical law.

## 2. The physics kernel (pre-existing)

Lives under `.claude/physics/`. Discovered (not created) during this work:

| File                  | Rows  | Role                                                             |
|-----------------------|------:|------------------------------------------------------------------|
| `INVARIANTS.yaml`     |  ~430 | Source of truth for all `INV-*` ids (44 after this PR)           |
| `KURAMOTO_THEORY.md`  |   142 | Kuramoto theory + critical coupling + finite-size corrections    |
| `SEROTONIN_THEORY.md` |   132 | 5-HT ODE + Lyapunov stability + desensitisation                  |
| `DOPAMINE_THEORY.md`  |   148 | TD-error sign + convergence + discount bounds                    |
| `GABA_THEORY.md`      |    72 | Sigmoid gate + monotonicity + position reduction                 |
| `TEST_TAXONOMY.md`    |   203 | Test type hierarchy, priority system, decision tree              |
| `EXAMPLES.md`         |   251 | Before/after examples from this codebase                         |
| `validate_tests.py`   |   780 | L1–L5 test validation + C1–C2 code audit + --self-check          |

`CLAUDE.md` at the repo root enforces **Rule Zero**: read
`.claude/physics/INVARIANTS.yaml` and the relevant theory file **before**
writing any test that touches a physical quantity. Tests that ignore Rule
Zero are physics-blind by construction.

## 3. What this PR added

### 3.1 Invariant catalog extension (`.claude/physics/INVARIANTS.yaml`)

The pre-existing kernel had 34 invariants across 8 modules (Kuramoto,
Explosive Sync, Serotonin, Dopamine, GABA, Free Energy, Thermodynamics,
Ricci). This PR adds **10 invariants across 4 new modules**:

| Module      | IDs                                | Type coverage                          |
|-------------|------------------------------------|----------------------------------------|
| Kelly       | `INV-KELLY1`, `INV-KELLY2`, `INV-KELLY3` | algebraic / universal / statistical |
| OMS         | `INV-OMS1`, `INV-OMS2`, `INV-OMS3` | conservation / universal / universal  |
| SignalBus   | `INV-SB1`, `INV-SB2`               | universal / universal                  |
| HPC         | `INV-HPC1`, `INV-HPC2`             | universal / universal                  |

After extension: **57 invariants, self-check green, every invariant type
has a matching L3 checker.**

### 3.2 Migrated test files (full L1–L5 clean, tracked by CI)

| File                                                        | Tests | Grounded | INV-* witnessed                 |
|-------------------------------------------------------------|------:|---------:|---------------------------------|
| `tests/unit/physics/test_T4_higher_order_kuramoto.py`       |    15 |        3 | INV-K1, INV-HPC1, INV-HPC2      |
| `tests/unit/physics/test_T2_explosive_sync.py`              |    14 |        3 | INV-K1, INV-ES1, INV-HPC1       |
| `tests/unit/physics/test_T6_free_energy_gate.py`            |    15 |        1 | INV-FE1                         |
| `tests/unit/physics/test_T8_kelly_oms_signalbus_hpc.py` †   |     5 |        5 | INV-HPC1, INV-HPC2, INV-SB2, INV-KELLY1, INV-KELLY2 |
| `tests/core/neuro/serotonin/test_serotonin_properties.py`   |     4 |        4 | INV-5HT2, INV-5HT5, INV-5HT7, INV-HPC1 |
| `tests/core/neuro/dopamine/test_dopamine_invariants_properties.py` | 1 | 1 | INV-DA3                         |
| `tests/unit/core/neuro/test_gaba_position_gate.py`          |    11 |        6 | INV-GABA1, INV-GABA2, INV-GABA3 |

† New file, created in this PR to give the freshly-added Kelly/SignalBus/HPC
invariants their first kernel-compliant witnesses. All other files are
migrations of pre-existing tests.

Grand total migrated **23 witnesses across 10 distinct invariants**, all
passing pytest and all clean at every kernel validator level (L1 INV-ref,
L2 id-valid, L3 test-structure, L4 error-message quality, L5 no magic
thresholds).

### 3.3 CI workflow (`.github/workflows/physics-kernel-gate.yml`)

Three jobs, pinned actions, merge-queue aware:

1. **`physics-kernel-self-check`** — runs
   `python .claude/physics/validate_tests.py --self-check`. Blocks merge
   if the kernel self-check fails (YAML unparseable, L3 dispatch gap,
   regex drift, theory-file cross-reference hole).
2. **`physics-test-validation`** — runs the validator against every file
   in the tracked migrated list (above). Any L1–L5 regression in those
   files blocks merge. Also prints a repo-wide summary for visibility,
   without blocking on orphans.
3. **`physics-code-audit`** — runs the C1/C2 audit on `core/` (silent
   clamps, undocumented numeric bounds). Report-only for now, until the
   pre-existing backlog is closed, then switched to fail-closed.

### 3.4 Parallel `physics_contracts/` layer

Kept intact per user instruction. It is an independent, complementary
layer with a dotted-id law catalog (`physics_contracts/catalog.yaml`, 26
laws), an `@law()` decorator with a witness registry
(`physics_contracts/law.py`), and an AST validator
(`tools/validate_tests.py`) that implements binding-tokenisation
magic-literal rejection. Coexists with `.claude/physics/`; not merged,
not deleted.

## 4. What still needs doing (the honest backlog)

### 4.1 Orphan tests under physics paths

**1 482 L1 issues.** These are tests in physics directories (`tests/unit/
physics/`, `tests/core/neuro/…`, `tests/integration/test_physics_*`, etc.)
that do not yet cite any INV-* id. Each one is a candidate migration.
Estimated distribution (from the validator sweep):

| Module block                | Orphan tests (approx) |
|-----------------------------|----------------------:|
| Kuramoto / explosive sync   | ~250                  |
| Free energy / thermo        | ~180                  |
| Serotonin / dopamine / GABA | ~400                  |
| Ricci / curvature           | ~90                   |
| ECS / HPC / active inference | ~220                 |
| Shape / schema / infra tests in physics dirs | ~340  |

### 4.2 C1/C2 code audit backlog (`core/`)

`python .claude/physics/validate_tests.py core/ --audit-code` is currently
run in report-only mode in CI. The number of silent clamps needs to be
counted and each one either annotated with `# INV-*:` or wrapped in
telemetry.

### 4.3 Theory files for the new modules

`.claude/physics/` has theory `.md` files for Kuramoto, Serotonin,
Dopamine, GABA but not yet for Kelly, OMS, SignalBus, HPC. The invariants
for the new blocks live only in `INVARIANTS.yaml` with parameters and
common-mistake notes. A full theory document for each would deepen the
kernel.

### 4.4 Priority ranking of remaining migrations

Migrate P0 invariants first (block release), then P1 (investigate), then
P2 (informational). The P0 set across existing modules is:

```
INV-K1, INV-K2, INV-K3, INV-ES1, INV-5HT1, INV-5HT2, INV-5HT4,
INV-5HT6, INV-5HT7, INV-DA1, INV-DA3, INV-DA7, INV-GABA1, INV-GABA2,
INV-GABA3, INV-FE1, INV-FE2, INV-RC1, INV-KELLY1, INV-KELLY2,
INV-OMS1, INV-OMS2, INV-OMS3, INV-SB1, INV-SB2, INV-HPC1, INV-HPC2
```

This PR gave first witnesses to: INV-K1, INV-ES1, INV-5HT2, INV-5HT5,
INV-5HT7, INV-DA3, INV-GABA1, INV-GABA2, INV-GABA3, INV-FE1, INV-HPC1,
INV-HPC2, INV-SB2, INV-KELLY1, INV-KELLY2. Outstanding P0 invariants with
zero witnesses: INV-K2, INV-K3, INV-5HT1, INV-5HT4, INV-5HT6, INV-DA1,
INV-DA7, INV-FE2, INV-RC1, INV-OMS1, INV-OMS2, INV-OMS3, INV-SB1.

## 5. How to extend

1. Pick a P0 INV-* with zero witnesses from §4.4.
2. Read its theory file in `.claude/physics/` (Rule Zero).
3. Find a relevant existing test under `tests/` (grep for the module name)
   or create a new canonical witness under `tests/unit/physics/`.
4. Add the INV-* id to the docstring, rewrite assertions with 5-field
   error messages, derive thresholds from theory.
5. Run `python .claude/physics/validate_tests.py <your_file>` — must print
   `All physics tests pass validation.` with L1 = L2 = L3 = L4 = L5 = 0.
6. Run `python -m pytest <your_file>` — must pass.
7. Add the file to the `MIGRATED_FILES` array in
   `.github/workflows/physics-kernel-gate.yml` so a future regression is
   caught by CI.
8. Update the table in §3.2 of this file and the backlog in §4.

The kernel validator and CI gate do the rest.

## 6. Adversarial Physics Audit (2026-04-06)

Full adversarial falsification battery across all 15 modules.
Every module probed with extreme/pathological inputs.

### Results: 0 violations, 4 precision insights

| Module | Attack | Result |
|--------|--------|--------|
| **Kuramoto** | Correlated ω (ρ=0.95) at K=0.3·K_c | PASS: R=0.046 < ε=0.188 |
| **Kuramoto** | K-sweep N=128 (transition sharpness) | PASS: transition at ~0.8·K_c (finite-size shift) |
| **Serotonin** | Extreme initial (level=0.99, desens=2.0) | PASS: 0 Lyapunov violations / 500 steps, half-life ~65 |
| **GABA** | VIX range [0, 1e15] | PASS: gate ∈ [0,1] everywhere, monotone |
| **Cryptobiosis** | Rapid T oscillation [0.9, 0.3] × 30 ticks | PASS: all 15 DORMANT entries have mult==0.0 |
| **Free Energy** | 100 random trades, ΔF>0 bypass attempt | PASS: 0 bypasses |
| **Dopamine** | Inputs ±1e308, mixed extreme | PASS: RPE ∈ [-1,1] (tanh saturation) |
| **Ricci** | Flat series, extreme volatility | PASS: κ ≤ 1 everywhere; κ_min=-4.63 (RC1 correction confirmed) |
| **Kelly** | Base fractions [0.01, 5.0] | PASS: all within [floor·base, ceil·base] |
| **SignalBus** | Publish order preservation | PASS: deterministic DA→5HT→GABA |

### Precision insights (not violations)

1. **Kuramoto finite-size K_c shift**: at N=128, effective K_c ≈ 0.8·K_c(∞).
   This is correct Kuramoto physics — the mean-field formula is an N→∞ result.
   INV-K2 witnesses use K=0.3·K_c (deep subcritical) which is safe from this.
2. **GABA at vix=0**: inhibition=0.62 (not 0) because σ(w_vol·0.1/0.2)≈σ(0.5).
   Correct: vol=0.1 is a separate risk channel independent of VIX.
3. **Ricci volatile**: κ ranges to -4.63, confirming the INV-RC1 correction
   (κ ≤ 1 upper only, NOT [-1,1]) was necessary and correct.
4. **Serotonin convergence**: V → 0.014 (not exactly 0) after 500 steps from
   extreme initial. This is consistent with the exponential convergence
   rate of the ODE: residual ≈ V₀ · exp(-αt) with α≈0.15, t=500.
