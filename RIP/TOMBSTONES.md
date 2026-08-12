# TOMBSTONES

One canonical entry per dead hypothesis / engineering failure. Every
entry is sha-anchored to a merged commit and carries a falsifier
(metric + procedure). `SUCCESS SCORE` is stated in plain words; where it
was literally zero it reads **успіх: 0**.

All entries derive only from in-repo evidence
(`research/calibration/grid_kuramoto/`, `research/ctc_falsify/`,
`research/systemic_risk/`). Nothing here is invented or padded. The
catalog is the complete set of genuine in-repo
NEGATIVE / FALSIFIED / superseded artifacts found by grep; if a class of
failure is not represented it is because no such artifact exists in the
tree.

---

## CALIB-GRID-001 — first-order identifier on second-order data

- **NAME** · CALIB-GRID-001
- **LINEAGE / PR** · PR #749 — `research(calib): CALIB-GRID-001 —
  external ground-truth Kuramoto calibration (NEGATIVE artifact)`
- **SHA** · `64ce6f55ca5fd39b2ae895be2c2ece2824b9eb4c`
- **ARTIFACT** · `research/calibration/grid_kuramoto/RESULTS.md`
  (ledger `ed8d409b7b222eb0…`)
- **BORN** · The hypothesis that the GeoSync `core.kuramoto.
  coupling_estimator` (MCP row regression) recovers the signed coupling
  matrix and natural frequencies of a known external ground truth
  (WSCC-9 swing model, Anderson & Fouad Ex. 2.6,
  `K_true = |V_i||V_j|B_ij` ×8).
- **CAUSE OF DEATH** · Falsified at `MEASURED` tier against the exact
  external truth. Metric = the five frozen pre-registered gates.
  Procedure = WSCC-9 → swing-equation trajectory (Störmer-Verlet,
  published inertia/damping, frozen θ₀) → estimator → gates.
  Result: `noiseless.frobenius = 1.0459` (gate ≤ 0.10, FAIL);
  `noiseless.critical_coupling = 1.0000` (gate ≤ 0.15, FAIL);
  `noisy.frobenius = 0.9901`; `noisy.topology_f1 = 0.8000`. Root cause
  localized: a first-order Kuramoto identifier applied to second-order
  swing data — the unmodeled inertial term `m_i θ̈_i` produces an
  antisymmetric residual `‖(K̂−K̂ᵀ)/2‖_F = 15.9` on a physically
  symmetric truth.
- **SUCCESS SCORE** · Partial-but-NEGATIVE. Topology support was
  recovered exactly (`noiseless.topology_f1 = 1.0` — *which* generator
  pairs are coupled). Signed weights, natural frequencies and critical
  coupling: **успіх: 0** (rel. errors at 1.0). Overall verdict
  `NEGATIVE`.
- **WHAT IT KILLED** · The infinite regress of "tune the estimator and
  it will recover the grid". It named the *model class* defect
  (first-order on second-order) instead, terminating estimator-tuning
  speculation and pointing at the structural fix.
- **REUSABLE LESSON** · An estimator that recovers topology but returns
  a large antisymmetric residual on a symmetric truth is not under-tuned
  — it is in the wrong model class. Measure the antisymmetric residual
  before tuning anything.

---

## CALIB-GRID-001-R1 — the double-differentiation causal claim
*(itself later FALSIFIED — see SUPERSESSIONS registry)*

- **NAME** · CALIB-GRID-001-R1
- **LINEAGE / PR** · PR #751 — `research(calib): CALIB-GRID-001 R1 —
  swing-aware estimator refinement (NEGATIVE, parent #749)`
- **SHA** · `a5527708833df308e67536aaa690b4f16e88dccd`
- **ARTIFACT** · `research/calibration/grid_kuramoto/r1/RESULTS.md`
  (ledger `c32011b89fc879ec…`)
- **BORN** · The swing-aware symmetric estimator closes the first-order
  / antisymmetric model-class defect, and the residual noisy failure is
  caused by a **double-differentiation second-derivative SNR /
  persistent-excitation boundary** — verbatim: *"No consistent
  estimator exists for the noisy regime at this trajectory length and
  excitation level"*.
- **CAUSE OF DEATH** · Two distinct falsifiers:
  1. R1's *own* gates stayed `NEGATIVE`: it flipped exactly one frozen
     gate (`noiseless.frobenius` 1.046 → 0.067, antisymmetric residual
     15.9 → 0.0 — the first-order defect genuinely closed), but
     `noiseless.critical_coupling = 0.4942` (gate ≤ 0.15) and
     `noisy.frobenius = 16.6071` (gate ≤ 0.25) still FAIL.
  2. Its **causal attribution** for the noisy failure was later
     **FALSIFIED** by CALIB-GRID-002 (sha
     `e71d1915233283452f3fb219aafabd2f19035371`): an estimator that
     *never* double-differentiates the phase (integral / weak form)
     still fails the same σ=0.02 regime at ≈0.95. The true cause is a
     **class-independent regressor-level SNR floor**, not a
     differentiation-operator defect. This supersession is recorded
     append-only in `research/calibration/grid_kuramoto/
     SUPERSESSIONS.md` / `SUPERSESSIONS.yaml` (SUPERSEDE-001),
     enumerating exactly the 4 sha-pinned artifacts that encode the
     stale claim and the 2 that cite it. The R1 artifact is **not
     edited**; it stands as the differential-class boundary record.
- **SUCCESS SCORE** · The engineering sub-result (closing the
  first-order / antisymmetric defect) is real and survives. The causal
  *claim* it asserted about the noisy regime: **успіх: 0** — falsified
  forward by CG002. Overall lineage verdict `NEGATIVE`.
- **WHAT IT KILLED** · It killed the "first-order on second-order"
  attribution from CALIB-GRID-001 (antisymmetric residual → 0.0). Its
  own noisy attribution then became the thing CG002 had to kill —
  terminating the "switch estimator class and the noise goes away"
  regress before lineage #6+ could inherit it.
- **REUSABLE LESSON** · A causal attribution inside a frozen NEGATIVE is
  itself a falsifiable claim. Pin it, and build the append-only
  supersession layer so a later lineage can falsify it *forward* without
  rewriting history.

---

## CALIB-GRID-002 — the integral / weak-form falsifiable claim

- **NAME** · CALIB-GRID-002
- **LINEAGE / PR** · PR #757 — `research(calib): CALIB-GRID-002 —
  integral/weak-form swing identifier (sha-pinned NEGATIVE, claim
  FALSIFIED, boundary relocated)`
- **SHA** · `e71d1915233283452f3fb219aafabd2f19035371`
- **ARTIFACT** · `research/calibration/grid_kuramoto/cg002/RESULTS.md`
  (ledger `d0f89e24341b0995…`)
- **BORN** · Pre-registered falsifiable claim: an integral / weak-form
  swing identifier that never double-differentiates the phase recovers
  signed coupling at the *same* frozen σ=0.02 / record length where the
  R1 differential estimator provably cannot, **and** the merged
  identifiability front-gate ACCEPTs the σ=0.02 case under the integral
  form.
- **CAUSE OF DEATH** · **FALSIFIED for the noisy regime.** Metric = the
  pre-registered `cg002.*` gates; procedure = the *same* frozen
  `SimConfig` (θ₀=0.6, seed 42) as CALIB-GRID-001. The class change
  improved noisy Frobenius 17.5× (R1 16.607 → integral 0.947) and did
  not regress noiseless (0.0666 → 0.0381), but `0.947 ≫ 0.25` (gate
  FAIL) and the front-gate still `REFUSE`s σ=0.02. A direct
  regressor-level SNR measurement on the frozen trajectory shows the
  clean `sin(θ_i−θ_j)` signal sits **below the σ=0.02 measurement
  noise on every edge**: SNR 0.493 / 0.085 / 0.563 on edges
  (0,1)/(0,2)/(1,2), *before any estimator touches the data*.
- **SUCCESS SCORE** · The estimator-class change closed **nothing the
  differential class could not**: on the falsifiable claim's own target
  (noisy σ=0.02), **успіх: 0**. What it *did* produce is the corrected,
  sha-pinned localization (class-independent regressor floor) — that is
  the conserved asset, not a "pass".
- **WHAT IT KILLED** · It killed R1's double-differentiation
  attribution (see SUPERSEDE-001) **and** the entire "find a better
  estimator class for the noisy regime" research direction: no swing
  identifier — differential, integral, or otherwise — can recover
  coupling the σ=0.02 noise has already destroyed at the frozen
  excitation. Closing it requires changing the *frozen experiment*,
  which CG002 is not permitted to do.
- **REUSABLE LESSON** · When a class change relocates rather than closes
  a boundary, measure the regressor SNR directly. A signal below the
  measurement noise is a property of the experiment, not the estimator —
  no class change can recover it.

---

## CALIB-GRID noisy.* regime — INFEASIBLE_BY_CONSTRUCTION
*(the canonical "успіх = 0" headstone)*

- **NAME** · CALIB-GRID noisy.frobenius / noisy.topology_f1 (σ=0.02)
- **LINEAGE / PR** · PR #764 — `governance(calib): F1 supersession
  registry + F2 pre-registration amendment (append-only, forward-only,
  zero estimator change)`
- **SHA** · `65666072003ec51b14a1322944d2ec9508615b6e`
- **ARTIFACT** ·
  `research/calibration/grid_kuramoto/PREREGISTRATION_AMENDMENT_001.md`
  / `.yaml` (rests on CG002 ledger `d0f89e24341b0995…`, merge
  `e71d1915`)
- **BORN** · The two frozen σ=0.02 gates (`noisy.frobenius ≤ 0.25`,
  `noisy.topology_f1 ≥ 0.90`) were pre-registered as if they *tested the
  estimator* — i.e. as pass/fail acceptance gates carrying information
  about estimator quality.
- **CAUSE OF DEATH** · CG002 proved (sha-pinned, regressor-level)
  `SNR < 0.6` on every edge before any estimator runs ⇒
  `P(FAIL) = 1 ∀ estimator` ⇒ the gate carries **H = 0 bits** about
  estimator quality. Scored as pass/fail, it makes every future
  lineage's `NEGATIVE` saturate to zero information. Amendment 001
  (append-only, forward-only, **zero threshold change**) reclassifies
  both gates from pass/fail acceptance to
  `INFEASIBLE_BY_CONSTRUCTION` — a distinct zero-bit state, **not** PASS,
  **not** FAIL.
- **SUCCESS SCORE** · **успіх: 0 — and this is the highest-information
  output in the entire register.** The noisy regime is not "not yet
  passed"; it is *proven information-theoretically unreachable* at the
  frozen θ₀ / record length. The zero is the result. It is honored here,
  not hidden, and is explicitly NOT promoted into `HONORS.md`.
- **WHAT IT KILLED** · It terminated the infinite regress permanently:
  no estimator, no class, no tuning, ever, closes this gate at this
  frozen experiment. It also killed the failure mode where a future
  lineage reads a 0-bit gate as a real FAIL and chases a fix that
  cannot exist.
- **REUSABLE LESSON** · A gate at an information-theoretically
  unreachable operating point must be reclassified as a 0-bit
  diagnostic, not scored as FAIL — forward-only, never by editing the
  frozen pre-registration. An honest impossibility proof outranks any
  number of green gates.

---

## CTC-FALSIFY-001 — in-silico CTC channel recoverability
*(negative with a recursive self-retraction)*

- **NAME** · CTC-FALSIFY-001 (L1 → L2 → C3 → C4 → C5)
- **LINEAGE / PR** · PR #750 (L2 residual layer, estimator self-kills)
  → PR #756 (consolidated negative-as-product)
- **SHA** · `eb521856dcacd5349c9aaa7251df25f8bed3544d` (#750) ·
  `f8c70ba1cbcff860cbe01790a2793647a9a24c6d` (#756 consolidation)
- **ARTIFACT** · `research/ctc_falsify/RESULTS.md`
- **BORN** · On a physics-grounded generative ground truth with a
  known, toggleable directed A→B gamma-phase channel, standard
  Communication-through-Coherence estimands recover that channel; and
  (C3) a privileged phase-offset estimator makes it "recoverable in
  principle".
- **CAUSE OF DEATH** · Two orthogonal standard CTC estimands
  (PLV-residual, time-reversed PSI) are **blind** to the channel by
  their own pre-registered gates. The C3 escape-hatch was then audited
  by **C4 (recursive self-audit) and FAILED its own gates**: Cohen's
  d ≈ 0.48 < 1.0; confound false-positive ≈ 0.47; 20/32 false channels
  at `channel_strength = 0`. The C3 "recoverable in principle"
  inference is **RETRACTED to scope**.
- **SUCCESS SCORE** · On separating the directed channel from confounds
  under adversarial audit: **успіх: 0** — no estimator tested (standard
  or privileged) admissibly separates it. What survives is a scoped,
  hypothesis-level negative; it is explicitly **not** a verdict on CTC
  theory and **not** a real-data result.
- **WHAT IT KILLED** · It killed its *own* escape-hatch (C3) via C4
  before that escape-hatch could be promoted, terminating the
  "privileged estimator rescues the claim" regress.
- **REUSABLE LESSON** · An escape-hatch inference must be put through
  the same adversarial gate as the claim it rescues. A recursive
  self-audit that retracts your own prior inference is a feature, not a
  failure.

---

## SYSTEMIC-RISK interbank phase-locking — UNTESTED on real data

- **NAME** · Interbank phase-locking precedes banking-crisis events
- **LINEAGE / PR** · PR #557 — `feat(research/systemic_risk):
  pre-registered Kuramoto-on-interbank falsification battery`
- **SHA** · `7716a25bb64fc2418779d1eae692939d56fe76d3`
- **ARTIFACT** · `research/systemic_risk/VALIDATION.md` (status row)
- **BORN** · Hypothesis: interbank phase-locking (Kuramoto order
  parameter on the interbank exposure network) precedes
  banking-crisis events on real data.
- **CAUSE OF DEATH** · Not dead — **explicitly UNTESTED**. `VALIDATION.md`
  tiers this row `HYPOTHESIS` / **Pending**, blocked on user-supplied
  e-MID 2009-2015 / BIS LBS / ECB MMSR data. The falsification machine
  itself is verified on both rails (lower rail: random scores
  HARD_FAIL at AUC ≈ 0.45; upper rail: injected +3σ pre-event signal
  HARD_PASS, `auc_ci_low ≥ 0.70`) — but the *scientific* claim has no
  verdict.
- **SUCCESS SCORE** · The instrument: defensible (both rails verified —
  see `HONORS.md` tiering of the machine, not the claim). The
  scientific claim: **успіх: 0 (no verdict — UNTESTED, not falsified,
  not confirmed)**. Recorded here so it is not silently promoted to a
  result.
- **WHAT IT KILLED** · Pre-emptively kills the promotion leak where a
  verified *machine* is reported as a verified *finding*. The machine is
  green; the hypothesis is untouched.
- **REUSABLE LESSON** · A fail-closed, dual-rail-verified instrument
  with no input data has produced exactly zero scientific information.
  Tier the instrument and the claim separately, always.

---

## CALIB-F3 — bit-exact cross-runner ledger reproduction is INFEASIBLE

- **NAME** · CALIB-F3
- **LINEAGE / PR** · PR #770 — `fix(calib): F3 — deterministic-reduction
  harness + derived forward ε; cross-runner bit-exactness proven
  infeasible`
- **SHA** · `9c8f539679a08e68c64cbc421907433a78e36b7a` *(diagnosis-bearing tree; the impossibility
  reproducer below runs verbatim from this anchor — the closing PR adds
  only the harness, the forward bound and this headstone)*
- **ARTIFACT** · `research/calibration/grid_kuramoto/_deterministic.py`
  (the harness + the derived forward bound and its derivation)
- **BORN** · The F3 working hypothesis (audit PR #762, consolidation
  #759): the calibration-ledger reproduction nondeterminism is
  **thread/BLAS-reduction-order** noise, therefore *removable* by pinning
  native pools to one thread + a fixed reduction order, after which the
  ledger is **bit-identical across CI runners** and the reproduction ε
  can be tightened to bit-exact (or a machine-eps bound).
- **CAUSE OF DEATH** · Falsified by direct measurement. numpy and scipy
  each bundle a *private, statically linked* `libscipy_openblas64` built
  with `DYNAMIC_ARCH`; OpenBLAS dispatches to a CPU-micro-architecture
  micro-kernel at library load (a *host-CPU* property, **not** a
  thread-pool property). Procedure: full ledger rebuilt single-threaded
  (`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`) with **only**
  `OPENBLAS_CORETYPE` varied over six micro-kernels (Haswell, Prescott,
  Nehalem, SandyBridge, Core2, Atom). Result: a *pinned ledger metric*
  diverged by a worst-case **relative `2.20e-9`** (cg002
  `front_gate_score`) while the pure-numpy reductions
  (`sum`/`mean`/`std`/`median`, numpy's own pairwise loop, not BLAS)
  were bit-identical. Bit-exact cross-runner reproduction therefore
  requires re-linking numpy/scipy against a reference BLAS — outside the
  calibration boundary. The "removable by thread-pinning" premise is
  dead.
- **SUCCESS SCORE** · Forcing bit-exact cross-runner reproduction:
  **успіх: 0** (proven infeasible in-process). This zero **is** the
  result — a proven impossibility, not a hidden failure. The honest
  second-best shipped alongside it: a single-thread deterministic
  harness (same-CPU bit-identical, verified N=5×) and a *derived*
  forward window `FORWARD_REL_TOL = 1e-8` — **100× tighter** than the
  legacy `1e-6` — with `1e-8 = ceil_decade(2.20e-9 × 4.5)` recorded in
  the harness docstring. Explicitly **not** promoted to `HONORS.md`.
- **WHAT IT KILLED** · The masking failure mode: a `1e-6` reproduction
  window ~6 orders of magnitude looser than the real noise floor, in
  which a genuine `1e-9..1e-6` numeric regression on a pinned metric
  passed undetected. Forward ledgers are now detected ~100× sharper,
  bounded at the *proven-irreducible* noise floor — no looser, no
  falsely-tighter.
- **REGIME SPLIT (honesty rail)** · The merged sha-pinned ledgers
  (`RESULTS.json/.md`, `ledger_sha256`, `PREREGISTRATION*`,
  `THRESHOLD_PROVENANCE`, `SUPERSESSIONS*`, `AMENDMENT_001`) were born
  under the OLD nondeterministic regime. They are **NOT recomputed, NOT
  overwritten, NOT retroactively claimed bit-exact**: their reproduction
  stays at the documented `LEGACY_REL_TOL = 1e-6`. Only *forward* ledger
  computations run under the harness at the tight derived window. This
  mirrors the F2 amendment / SUPERSEDE-001 discipline: historical record
  immutable, ε documented as legacy-regime, forward = deterministic+tight.
- **REUSABLE LESSON** · A static `DYNAMIC_ARCH` BLAS makes in-process
  bit-exact cross-runner FP reproduction impossible by construction;
  the correct response is a *derived, measured* tolerance bounded by the
  irreducible micro-kernel noise floor, not an arbitrary loose window
  and not a forced determinism claim that the wheels cannot honour.

---

*End of register. Seven entries. The complete in-repo set of genuine
NEGATIVE / FALSIFIED / superseded / UNTESTED / INFEASIBLE artifacts found
by grep (`RETRACTION`, `NEGATIVE`, `NO_ADMISSIBLE`, `null`, `falsif`,
`superseded`, `INFEASIBLE`, pre-registration ledgers, RESULTS.json
verdicts). No entry was padded; the catalog is the evidence.*
