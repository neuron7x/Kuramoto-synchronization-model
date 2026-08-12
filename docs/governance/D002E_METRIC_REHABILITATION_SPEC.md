# D-002E Metric Rehabilitation Protocol — `tau_onset` & `phase_lag`

## Context

The canonical D-002C run produced a synthetic PASS scoped to the
`sync_auc` metric. `tau_onset` and `phase_lag` were excluded by the
POS preflight gate (signal_ci_ratio ≤ 2.0 at N=400, λ=1.0, n_seeds=50,
on KNOWN strong precursor — three substrates × two metrics = 6 combos
all EXCLUDE).

This exclusion is a **scope narrowing**, not a science failure. It
tells us the metrics, as currently implemented, are operationally
underpowered at the D-002C grid. They are NOT supported by the
canonical PASS.

## Non-goals

- ❌ Rescue `tau_onset` / `phase_lag` for D-002C canonical scope.
- ❌ Retune POS preflight threshold to "let them through".
- ❌ Modify `D002C_PREREGISTRATION.yaml`.

## Diagnostic protocol (separate research thread, NOT a D-002C launch blocker)

For each of `tau_onset` and `phase_lag`:

### Step 1 — Sensitivity to N

Run the metric on synthetic R(t) trajectories at N ∈ {50, 100, 200,
400, 800, 1600}. Plot:

- `signal_ci_ratio(N)` curve under strong precursor (λ=1.0)
- `signal_ci_ratio(N)` curve under medium precursor (λ=0.40)
- `signal_ci_ratio(N)` curve under weak precursor (λ=0.05)

Question: does `signal_ci_ratio` grow with N (statistical power),
or does it stay flat (estimator-bound)?

### Step 2 — Estimator stability

Run the metric on a fixed R(t) trajectory across n_bootstrap ∈ {4, 16,
64, 256, 1024}. Measure:

- bootstrap CI width vs. n_bootstrap
- direction stability across resampling

Question: is the estimator's CI converging? Or does it remain wide?

### Step 3 — CI width vs. signal width

For the most favourable cell (largest N, largest λ, strongest substrate),
compute:

- `CI_half_width / |signal_mean|` ratio
- compare to `sync_auc` baseline ratio at the same cell

Question: is the metric's CI structurally too wide relative to its
signal, OR is the signal itself the bottleneck?

### Step 4 — Saturation / discreteness

For `tau_onset` specifically: the metric is a first-crossing time
in a discrete sample grid. Investigate:

- censoring fraction at the swept N
- discreteness floor (smallest nonzero τ value)
- Kaplan-Meier RMST estimator behaviour at >50% censoring

For `phase_lag`: investigate:

- whether the reference (substrate principal eigenvector) is
  numerically degenerate at small N
- whether the threshold (0.50) is operationally reachable in window

### Step 5 — Power calculation

Given the empirical CI distribution, compute the theoretical minimum
N needed for the metric to satisfy `signal_ci_ratio > 2.0` under the
strong-precursor regime. If that N exceeds 800, the metric is
operationally inapplicable to the D-002C N ≤ 200 envelope.

## Acceptance criteria (D-002E)

D-002E produces a verdict per metric:

- **REHABILITATED** — diagnostic shows the metric is fixable
  (e.g., wider window, better estimator, different threshold)
  AND a redesigned variant passes a small validation sweep at
  N ∈ {50, 100, 200} signal_ci_ratio > 2.0.
- **OPERATIONALLY INAPPLICABLE** — diagnostic shows the metric
  requires N > 800 or fundamentally different protocol to be
  powered.
- **REQUIRES PRE-REGISTRATION REVISION** — diagnostic shows the
  current threshold / window / reference assumption is unsound.
  In this case a fresh pre-registration (NOT an edit) is required
  before D-002E can supply rehabilitated metrics to a future
  D-002C variant.

## Claim boundary on D-002E

This is a **diagnostic + redesign protocol**, not a claim layer.
D-002E outputs:

- power curves (numeric artifacts)
- a per-metric verdict (REHABILITATED / OPERATIONALLY INAPPLICABLE /
  REQUIRES PRE-REGISTRATION REVISION)
- a list of recommended redesign actions

D-002E does NOT promote any verdict tier and does NOT modify the
existing canonical D-002C claim ledger. If a metric is
REHABILITATED, a follow-up D-002C variant (under a fresh
pre-registration with the redesigned metric) would be the path to
extending the canonical claim.

## Priority

D-002E is **P4** in the current priority stack:

| Priority | Item | Status |
|---|---|---|
| P0 | Freeze canonical D-002C result | this PR |
| P1 | C2.4-A2: per-seed payload data contract | pending |
| P2 | Post-C2.4-A2 canonical rerun | pending |
| P3 | R2-B: non-trivial false-positive control | pending |
| **P4** | **D-002E metric rehabilitation** | **pending (this spec)** |
| P5 | #670 Clock DI reliability hardening | pending |
