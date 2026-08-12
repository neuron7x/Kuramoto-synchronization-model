# HONORS — defensible engineering / methodological results

> **READ THIS FIRST.** These are **engineering / methodological
> results, NOT scientific discoveries.** No claim here is "validated",
> a "breakthrough", or "proven science" — those words are forbidden in
> this file by construction. The highest-information output of the
> entire CALIB-GRID arc is the **noisy-regime impossibility proof**
> (`noisy.*` INFEASIBLE_BY_CONSTRUCTION). That result lives in
> `TOMBSTONES.md`, **not here**, because it is a kill, not a win — and
> the kill is worth more than every entry below.
>
> This file is sharply and deliberately separated from the cemetery.
> The separation is unblurrable: different file, explicit header, no
> cross-promotion. An entry qualifies here **only** if it is a
> defensible engineering or methodological artifact, sha-anchored, with
> no scientific claim attached.

## Admissibility tiers

- **ENGINEERING-VALIDATED** — an executable, sha-anchored engineering
  property that holds by construction or by an external proven
  reference; verifiable by running the repo. NOT a science claim.
- **METHODOLOGICAL** — a process / governance property (fail-closed,
  append-only, byte-frozen) demonstrable from the artifact and its
  tests. NOT a science claim.

---

## (a) Externally-calibrated, self-aware identifiability front-gate

- **TIER** · ENGINEERING-VALIDATED
- **LINEAGE / PR** · PR #755 — `feat(kuramoto): graded swing
  identifiability front-gate (reliability infra, NOT a science claim)`
- **SHA** · `a5e0d533b2201c999b31c792773e858f8da713bf`
- **ARTIFACT** ·
  `research/calibration/grid_kuramoto/identifiability/RESULTS.md` +
  `THRESHOLD_PROVENANCE.md`
- **WHAT IS DEFENSIBLE** · The instrument is calibrated against the
  *proven* Dörfler–Bullo critical-coupling reference (the analytic
  formula is verified exact to 1e-12 in `test_dorfler_bullo_*`) **and**
  is self-aware: at the σ=0.02 operating point it emits a typed
  `REFUSE` instead of the ~20×-biased point estimate the parent
  lineages exposed. The REFUSE threshold was committed *before* the
  validation and is bound by a no-peek drift test.
- **EXPLICIT NON-CLAIM** · This does **not** close the frozen
  `noisy.frobenius` gate — the noisy regime stays NEGATIVE
  (see `TOMBSTONES.md`). The honored property is narrow: the
  instrument *knows* it fails out-of-envelope and *says so*. That is
  reliability infrastructure, not a science result.

---

## (b) The fractal-generator kill as an executable invariant

- **TIER** · ENGINEERING-VALIDATED
- **LINEAGE / PR** · PR #762 (lineage-scale architectural forcing
  functions) → PR #767 (module-scale AST forcing function)
- **SHA** · `e6370fe3e9a519982176852b3ac15a77e2bc1ab9` (#762) ·
  `89e4c0285ecf0dd4c79f8dc3efa3a61fe1c95029` (#767)
- **ARTIFACT** ·
  `tests/research/calibration/test_calib_lineage_forcing_functions.py`
  (#762) ·
  `tests/research/calibration/test_kuramoto_coupling_strategy_registry.py`
  (#767)
- **WHAT IS DEFENSIBLE** · The "stop the fractal/dynamical generator
  duplication" decision was not left as prose — it was installed as a
  **negative-feedback control law executed as a test**: at lineage
  scale a forcing function fails closed if a new doc inherits a
  superseded premise without resolving the registry; at module scale an
  AST-level forcing function constrains the coupling-estimator strategy
  surface. The control law is the deliverable, and it is executable.
- **EXPLICIT NON-CLAIM** · This says nothing about whether the
  Kuramoto inverse problem is solvable. It is a software-architecture
  invariant that prevents a known failure mode from recurring.

---

## (c) Bit-identical strategy-registry refactor

- **TIER** · ENGINEERING-VALIDATED
- **LINEAGE / PR** · PR #767 — `refactor(kuramoto): swing
  coupling-estimator strategy registry (F4 — module-scale forcing
  function)`
- **SHA** · `89e4c0285ecf0dd4c79f8dc3efa3a61fe1c95029`
- **ARTIFACT** · `core/kuramoto/coupling_estimator.py` +
  `tests/research/calibration/test_kuramoto_coupling_strategy_registry.py`
  (`test_golden_vectors_bit_identical`)
- **WHAT IS DEFENSIBLE** · The estimator was refactored into a strategy
  registry with **all 25 path hashes pinned to the parent sha
  `65666072`** (the bit-identical proof), **zero importer edits**, and a
  read-only public view with fail-closed duplicate-key registration.
  The frozen sha-pinned calibration artifacts stay byte-frozen and are
  enumerated in the diff-bound commit acceptor's `forbidden_paths`.
- **EXPLICIT NON-CLAIM** · A behavior-preserving refactor proven
  bit-identical by 25 golden hashes is an engineering property, not a
  result about the physics. It changed how the code is organized and
  proved it changed nothing observable.

---

## (d) A fail-closed falsification machine with append-only supersession

- **TIER** · METHODOLOGICAL
- **LINEAGE / PR** · PR #764 — `governance(calib): F1 supersession
  registry + F2 pre-registration amendment (append-only, forward-only,
  zero estimator change)`
- **SHA** · `65666072003ec51b14a1322944d2ec9508615b6e`
- **ARTIFACT** · `research/calibration/grid_kuramoto/SUPERSESSIONS.md` /
  `.yaml` + `PREREGISTRATION_AMENDMENT_001.md` / `.yaml`
- **WHAT IS DEFENSIBLE** · The methodological result *itself*: a
  falsification pipeline where a falsified causal attribution is
  superseded **forward only** — the historical NEGATIVE / FAIL records
  stay byte-identical, never edited or recomputed, and a forcing
  function fails closed if a new lineage inherits a superseded premise.
  History is conserved, not rewritten. This is the discipline that
  makes every tombstone in `TOMBSTONES.md` trustworthy.
- **EXPLICIT NON-CLAIM** · This is a process property. It does not make
  any of the superseded claims true; it makes the *record* of their
  falsification immutable and reusable.

---

> **Closing note (unblurrable separation).** Nothing in this file is a
> scientific finding. The instruments are sound; the science is in
> `TOMBSTONES.md`, and there it is overwhelmingly negative — by design.
> The noisy-regime impossibility proof is the result GeoSync is least
> ashamed of, and it is a tombstone, not an honor. That ordering is
> intentional and is the whole point of this directory.
