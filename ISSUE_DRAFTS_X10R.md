# X-10R post-PR-#635 issue drafts

This file is the canonical fallback for GitHub issues that the
X-10R execution protocol requires the PR author to open. When
remote issue creation isn't available from inside the agent,
these drafts are committed alongside the code so that they
travel with the PR and are visible to the reviewer.

Created: 2026-05-09 (alongside PR #635, branch
`feat/x10r-cimini-squartini`).

---

## Issue 1 — Reciprocity-aware positive controls for spectral recovery

**Title.** `X-10R debt: reciprocity-aware positive controls for spectral recovery`

**Labels.** `x10r-debt`, `scientific-validity`, `research`, `priority/before-real-bis-data`

**Assignee.** Yaroslav Vasylenko (@neuron7xLab)

**Tracked TODO.** `TODO_PR_RECIPROCITY_AWARE_CONTROLS` in
`research/reconstruction/positive_control.py` module docstring (FIX B6).

**Repayment trigger.** BEFORE the first Gate 6 verdict on real BIS LBS data.

### Body

The current sweep in `positive_control.run_recovery_on_substrate`
varies only **density** (`{0.03, 0.05, 0.08, 0.12}`). The 2024
e-MID-based interbank reconstruction literature establishes
**reciprocity** as a *separable* structural feature whose
explicit enforcement materially improves recovery of spectral
properties — including the largest real eigenvalue, which is the
exact quantity Gate 6 (Kuramoto precursor) inherits via
`_normalise_to_unit_spectral_radius` and `_kc_lorentzian_proxy`.

**Why this matters.** A density-only certificate may pass for a
target reconstruction class that is *spectrally* mis-specified.
On real BIS data, a Gate 6 verdict against such a certificate
would inherit the spectral mis-specification silently — the
precursor would be benchmarked against the wrong null.

**Repayment plan.**

1. Extend the sweep in `run_recovery_on_substrate` to a
   `density × reciprocity` grid (suggested reciprocity grid:
   `{0.0, 0.25, 0.5, 0.75}` measured by the link-level reciprocity
   ratio of the *ground truth* substrate).
2. Generate reciprocity-conditioned ground-truth substrates
   (extend `ground_truth_core_periphery`,
   `ground_truth_hierarchical`, and `ground_truth_ba` with a
   `reciprocity` parameter that tunes the bidirectional-edge
   probability).
3. Audit recovery on each `(d, r)` cell; populate
   `GroundTruthRecoveryCertificate.tested_at_reciprocity` with
   the reciprocity grid points that passed.
4. Update `check_domain_of_validity` to gate on reciprocity when
   the certificate carries it — the gate already compares
   measured `Pearson(s_out, s_in)` against the certified envelope
   when `tested_at_reciprocity` is non-empty.
5. Document the closed envelope in
   `cimini_squartini.py` / `positive_control.py` docstrings; bump
   the InstrumentScope `valid_for_n_nodes` only after the new
   evidence surface lands.

**Definition of done.**

- `GroundTruthRecoveryCertificate.tested_at_reciprocity` is non-empty
  on the canonical CP / hierarchical / BA-m=5 substrates.
- A new test `test_reciprocity_aware_recovery_certificate.py`
  proves Gate 5 holds across the `(d, r)` grid for at least one
  substrate.
- The Gate 6 verdict on the canonical sweep changes by at most
  `min_precursor_gap` after the reciprocity prior is applied
  (proves the prior is sharp enough to matter without flipping
  signs everywhere).

**Anchors.**

- Cimini, Squartini, Garlaschelli, Gabrielli (2015), Sci. Rep. 5:15758.
- Squartini & Garlaschelli (2017), "Maximum-entropy networks", §6.2.
- 2024 reciprocity-aware reconstruction follow-up — pin exact
  citation when literature search re-runs.

---

## Issue 2 — Operational-regime fidelity TODO promotion

**Title.** `X-10R debt: weighted_allocation unit tests cover uniform Bernoulli, not Cimini-calibrated p_ij`

**Labels.** `x10r-debt`, `tech-debt`, `tests`, `priority/before-real-bis-data`

**Assignee.** Yaroslav Vasylenko (@neuron7xLab)

**Tracked TODO.** `TODO_PR_NEXT (operational-regime fidelity)` in
`research/reconstruction/weighted_allocation.py` module docstring.

### Body

The unit tests in `tests/reconstruction/test_weighted_allocation.py`
exercise `allocate_weights` under uniform-Bernoulli p (e.g., `p=0.30`)
supports — NOT the Cimini-calibrated heterogeneous `p_ij` that the
operational pipeline generates from `fit_cimini_squartini`.

The two regimes differ in IPF feasibility: uniform supports converge
crisply, but Cimini-calibrated supports concentrate edges on
top-fitness pairs and can leave structural residual on heavy-tailed
marginals (BIS LBS country aggregates exhibit lognormal-like
distributions). Gate 5 catches any residual at the verdict boundary,
so this is *debt*, not a *bug* — but the test surface does not yet
faithfully simulate the operational regime.

**Repayment plan.**

1. Regenerate test fixtures from `fit_cimini_squartini` on each X-10R
   density target (`{0.03, 0.05, 0.08, 0.12}`).
2. Add a parametric IPF-residual test under the Cimini-calibrated
   regime; assert max(row_L1, col_L1) ≤ Gate 5 thresholds.
3. Keep one uniform-Bernoulli baseline test as a smoke / regression
   anchor.

**Definition of done.**

- New test `test_weighted_allocation_under_cimini_regime.py` exists
  and passes under PostToolUse (ruff format, ruff check, mypy --strict).
- Gate 5 passes on at least 3 of 4 sweep densities under the
  Cimini-calibrated regime for the canonical CP substrate at N=200.

---

## Issue 3 — Country-to-bank marginal allocator (Phase C epic X-10R-1)

**Title.** `X-10R epic: country-to-bank marginal allocator (BIS LBS → bank-level marginals)`

**Labels.** `x10r-epic`, `scientific-validity`, `research`, `priority/strict-blocker-for-bank-level-claims`

**Assignee.** Yaroslav Vasylenko (@neuron7xLab)

**Estimated scope.** 6–10 PRs.

### Body

BIS LBS marginals are residence-based, country-aggregate, and
include intragroup positions. The current PR #635 reconstruction
target object on real BIS inputs is therefore the **latent
country-aggregate exposure network**, NOT a bank-level interbank
network (see `cimini_squartini.py` docstring §"TARGET OBJECT" and
INV-IDENTIFICATION-1).

Bank-level inference is a *separate* two-step inverse problem:
first split country aggregates into bank-level marginals using a
country-to-bank allocator with its own prior, then run the
existing Cimini-Squartini reconstruction on the bank-level
marginals.

**HALT condition.** Do not advertise X-10R as "bank-level inference
from BIS" until this epic lands.

**Prior sources for the allocator.**

- ECB Monetary Financial Institutions list (continuously
  maintained at the bank-name + country level).
- EBA transparency exercise — supervisory-style disclosures for
  119 banks across 25 EU/EEA countries.
- Commercial source (e.g., Moody's BankFocus / Orbis Bank Focus)
  for global bank-size priors and country-to-bank distribution
  quantiles.

**Validation surface.** The allocator needs its own positive
controls: synthetic country aggregates with known bank-level
marginals, recovery audit, density / heterogeneity / reciprocity
sweep — all the X-10R machinery that exists for the network
reconstruction must be re-applied at the allocator stage.

**Output contract.** Per-bank `s_in`, `s_out` vectors with
provenance (which prior was used, which country, which reporting
period, which fallback policy if priors are missing).

**Definition of done.**

- Allocator module lives under `research/reconstruction/allocator/`.
- Independent positive / negative controls.
- Capsule emits a *separate* allocator capsule alongside the
  reconstruction capsule, with its own `tested_at_*` evidence
  surface.
- Domain-of-validity check on real BIS extends to the allocator
  envelope (so a real BIS run is `WITHIN_VALIDATED_DOMAIN` only
  if BOTH allocator and reconstruction certify it).

---

## Issue 4 — BIS CBS as alternative substrate (Phase C epic X-10R-3)

**Title.** `X-10R epic: BIS CBS reconstruction as alternative to LBS (nationality-based)`

**Labels.** `x10r-epic`, `research`, `priority/post-allocator`

**Assignee.** Yaroslav Vasylenko (@neuron7xLab)

### Body

BIS Consolidated Banking Statistics (CBS) are nationality-based,
focus on the *parent* banking group, and exclude intragroup
positions. CBS is therefore conceptually closer to a
"bank-group node" ontology than LBS, and reduces (without
eliminating) the country-to-bank ontology drift.

**Scope.** Run the X-10R reconstruction on CBS marginals
alongside LBS; compare recovered network classes and Gate 6
verdicts. CBS still requires the country-to-bank allocator
(epic X-10R-1, Issue 3) because CBS is also country-level
reporting — but the allocator prior on CBS may be tighter
because CBS already excludes intragroup noise.

**Definition of done.**

- A side-by-side comparison study (CBS vs LBS reconstruction)
  with capsule output for each.
- Documented decision rule for which substrate to anchor any
  bank-level forward signal on.

---

## Issue 5 — Governance layer (Phase C epic X-10R-4)

**Title.** `X-10R epic: governance layer (RO-Crate, OSF, AsPredicted, Workflow Run RO-Crate)`

**Labels.** `x10r-epic`, `governance`, `priority/publication-readiness`

**Assignee.** Yaroslav Vasylenko (@neuron7xLab)

### Body

After the science is fixed (epics X-10R-1 and X-10R-2), wrap the
end-to-end pipeline in machine-readable provenance:

- RO-Crate 1.2 metadata writer for every capsule.
- Workflow Run RO-Crate provenance for the full
  reconstruction → Gate 5 / 6 → capsule pipeline.
- OSF secondary-data preregistration template for the X-10R real-data
  protocol.
- AsPredicted concise prereg for hypotheses + decision rules,
  pinned at PR-time.

This is **publication-readiness** layer, not method-validity layer.
Do NOT pull this forward over X-10R-1 or X-10R-2.

**Definition of done.**

- Capsule writer also emits an RO-Crate-1.2-compliant manifest.
- A real-data dry run produces an OSF / AsPredicted prereg PDF /
  HTML alongside the capsule.

---

## Mapping to Phase C epics in the execution protocol

| Issue | Phase C epic | Strict blocker for |
|-------|-------------|--------------------|
| 1     | X-10R-2 (reciprocity-aware) | first Gate 6 on real BIS |
| 2     | (operational-regime fidelity TODO promotion) | first Gate 6 on real BIS |
| 3     | X-10R-1 (country-to-bank allocator) | any bank-level claim |
| 4     | X-10R-3 (CBS comparison) | post-allocator |
| 5     | X-10R-4 (governance) | publication |

---

## Why this file exists (procedure note)

The X-10R execution protocol section *PHASE C — DEFERRED EPICS*
requires that these issues be visibly tracked. When the agent
running the protocol cannot reach the GitHub Issues API (no
permission, no auth, network limits), the same content is
committed in this file so that:

* the PR review surface still contains the deferred-epic list,
* the reviewer can rubber-stamp these to GitHub later from a
  single source of truth, and
* the PR does not block on a pure-write side-effect that the
  agent is structurally unable to perform.

If the issues are subsequently created on GitHub, replace each
section's "Body" header with a `→ #<issue-number>` link rather
than deleting the section — the file is the audit trail.
