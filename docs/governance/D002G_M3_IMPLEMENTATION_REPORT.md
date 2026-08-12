# D-002G-M3 — Implementation report

## 1. Scope

This PR (`feat/x10r-d002g-m3-topology-conditioned-null`) implements
the M3 null-admissibility infrastructure pre-registered at the merge
commit of PR #680. It ships:

* M3 dataclasses, exceptions, RNG salt 523, locked tolerance constants;
* the locked-marginal-set extractor `extract_m3_topology_summary`;
* the matched-density generator `topology_matched_resample` with a
  locked iteration cap;
* the 5-criterion eligibility ladder `verify_m3_eligibility`;
* the realisation function `realize_m3_null` and the dispatch path
  through `realize_null(strategy="M3_TOPOLOGY_CONDITIONED")`;
* ≥ 30 tests across verdict ladder / invariants / negative controls /
  adversarial traps / no-promotion gates;
* the eligibility matrix doc + machine-readable JSON;
* a fresh §B1.M3 blocker subsection;
* a `commit_acceptors/` YAML for diff-bound enforcement.

Strict scope. No canonical D-002G run. No D-002G PASS claim. No
D-002C ledger touch. No B2 closure. No M3 pre-reg edit.

## 2. Pre-registration anchor

* Pre-registration document: `docs/governance/D002G_P3_M3_PREREGISTRATION.md`
* Anchor sha (PR #680 squash-merge commit): `0f4433e04c7a594fc80c964eeec337a8b1128038`
* Anchor sha256 of the pre-reg doc itself: `0f11a0c890374c35e4dedecc66caec52ae867f49a8f8b3be2374f1464712c1f8`
* Touching the pre-reg in this PR = fresh M4, not an M3 implementation
  PR. Tested via
  `tests/systemic_risk/test_d002g_m3_no_promotion.py::test_m3_p3_m3_prereg_unchanged`.

## 3. Mechanism family (locked verbatim from M3 pre-reg §2)

> **M3 — topology-conditioned independent realisation under
> matched-density resampling**.
>
> Core idea: instead of permuting payload values WITHIN a fixed
> substrate realisation (the M2 contract), M3 constructs the null
> cohort by drawing an INDEPENDENT realisation from a TOPOLOGY-MATCHED
> generator whose marginals match the precursor's marginals at the
> canonical injection slice.

## 4. Locked marginal set

Per M3 pre-reg §2 + §9.1 forbidden refinement scope: the marginal set
itself is LOCKED. This PR refines only the concrete estimator + the
generator engineering, NEVER the marginal definition.

Marginal-set (locked):

1. Degree sequence — sorted-ascending tuple of per-node row-sum
   magnitudes, length N.
2. Block-label histogram — bin counts over the substrate-defined
   block-label space. Length-1 fallback `(N,)` when no labels exposed.
3. Spectral radius / N — `max(|eigvals(K)|) / N`.
4. Density — `|{(i,j) : i<j, |K[i,j]| > 1e-12}| / (N·(N-1)/2)`.

## 5. RNG salt 523 + deterministic seed contract

* `M3_TOPOLOGY_CONDITIONED_SALT: Final[int] = 523` — locked at M3
  pre-reg §9. Distinct prime from `NULL_SEED_OFFSET=10000`,
  `M6_PLACEBO_SALT=99`, `M2_PLACEBO_SALT=211`, `M2_NODE_PAYLOAD_SALT=313`,
  `M2_INJECTION_SEQUENCE_SALT=419`.
* All M3 RNG draws flow through
  `np.random.default_rng(deterministic_mix_multi(base_seed,
  M3_TOPOLOGY_CONDITIONED_SALT, null_seed, substrate_id_hash, N,
  lambda_bits))`. No global state. No `random.random()`. No
  time-based seeds.
* `deterministic_mix_multi` is a strict extension of the 2-arg
  `deterministic_mix` to N inputs — same sha256-low-63 primitive,
  parameterised over arity. The 2-arg ABI is preserved for M1/M2/M6
  callers.

## 6. Tolerance constants (declared BEFORE results)

Per M3 pre-reg §9.1 — the tolerance band is pinned in source as
`Final[float]` constants AND in this report's body BEFORE any
substrate verdict was observed. Post-hoc relaxation is forbidden by
M3 pre-reg §9.1 (forbidden refinement scope).

| Constant | Value |
|---|---:|
| `M3_TOL_MARGINAL` | 0.05 |
| `M3_TOL_NON_DEGENERATE` | 1e-3 |
| `M3_TOL_DENSITY` | 0.02 |
| `M3_TOL_SPECTRAL_RADIUS` | 0.05 |
| `M3_TOL_DEGREE_WASSERSTEIN` | 0.05 |

Additional locked constants:

| Constant | Value | Purpose |
|---|---:|---|
| `M3_GENERATOR_MAX_ITERATIONS` | 100 | matched-resample inner-loop cap |
| `M3_PRECURSOR_ENSEMBLE_SIZE` | 100 | precursor-specificity ensemble size |

If these defaults prove too strict and every substrate fails, the
truthful response is a fresh M4 pre-registration (NOT a tolerance
edit in this PR).

## 7. Eligibility criteria (5 hard gates)

Implemented in `verify_m3_eligibility`. First failing criterion wins;
the verifier returns immediately with the corresponding INELIGIBLE
literal.

1. **Topology marginal extractable** — substrate produces a valid
   K_precursor at this cell; shape (N,N), float64, finite, symmetric.
2. **Matched generator exists** —
   `topology_matched_resample(target=summary_of_K_p, null_seed)`
   converges within `M3_GENERATOR_MAX_ITERATIONS=100`.
3. **Identifiable from precursor** — over 100 distinct precursor seeds
   (0..99), ≥ 50 / 99 adjacent-seed pairs yield distinct degree
   marginals (degree-Wasserstein > tol_marginal / 10).
4. **Non-degenerate Frobenius distance** —
   `‖K_null − K_p‖_F > M3_TOL_NON_DEGENERATE`.
5. **Topology-coupling decoupled** — a non-identity node permutation
   preserves the M3 marginal summary inside the comparator tolerance
   (necessary, not sufficient).

## 8. Failure states (verdict ladder)

The locked Literal enum (one verdict per cell):

* `ELIGIBLE_M3`
* `INELIGIBLE_M3_MARGINAL_MISMATCH`
* `INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC`
* `INELIGIBLE_M3_DEGENERATE_DISTANCE`
* `INELIGIBLE_M3_GENERATOR_DIVERGENT`
* `INELIGIBLE_M3_TOPOLOGY_SUMMARY_MISSING`
* `INELIGIBLE_M3_NUMERICAL_NONFINITE`
* `INELIGIBLE_M3_SHAPE_CONTRACT_VIOLATION`
* `INDETERMINATE_M3_PROVENANCE_MISSING`

## 9. Negative controls (NC-M3-1..4)

`tests/systemic_risk/test_d002g_m3_negative_controls.py`:

* **NC-M3-1** — synthetic substrate with seed-invariant marginals →
  `INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC`.
* **NC-M3-2** — `M3TopologySummary` with contradictory marginals
  (zero degree sequence but positive support count) →
  `M3GeneratorDivergentError`.
* **NC-M3-3** — substrate whose K_null collapses to K_p →
  one of `{DEGENERATE_DISTANCE, NON_PRECURSOR_SPECIFIC, MARGINAL_MISMATCH}`
  (all three are truthful refusals; only ELIGIBLE_M3 is forbidden).
* **NC-M3-4** — substrate whose `realize()` raises →
  `INDETERMINATE_M3_PROVENANCE_MISSING`.

## 10. Adversarial traps

`tests/systemic_risk/test_d002g_m3_traps.py`:

* T1 — fake marginal match (contradictory target) rejected.
* T2 — degree-Wasserstein drift detected by comparator.
* T3 — summary sha cannot be forged independent of marginals.
* T4 — non-finite K_precursor → `INELIGIBLE_M3_NUMERICAL_NONFINITE`.
* T5 — seed-collision distinctness: same seed → bit-identical K_null;
  different seed → DIFFERENT K_null.
* T6 — global RNG monkey-patch has no effect on M3 output.
* T7 — INELIGIBLE substrates raise `M3NotEligibleError`; no silent
  downgrade to M1 / M2.
* T8 — claim-leakage forbidden-phrase scan over M3 module + docs.
* T9 — no `artifacts/d002g/canonical/` writes from M3.
* T10 — `D002C_CLAIM_LEDGER.yaml` sha pin invariant under full
  verifier-matrix execution.
* Bonus — salt-distinctness vs prior salts (99 / 211 / 313 / 419).

## 11. Eligibility matrix

See `docs/governance/D002G_M3_ELIGIBILITY_MATRIX.md` (long-form) and
`artifacts/d002g/m3/m3_null_domain_verdicts.json` (machine-readable).

Summary of empirical M3 verdicts on the locked prereg grid:

| Substrate | N=50 | N=100 | N=200 |
|---|---|---|---|
| `ricci_flow` | ELIGIBLE_M3 | ELIGIBLE_M3 | ELIGIBLE_M3 |
| `block_structured` | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC |
| `temporal_coupling` | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC |

## 12. B1 status (computed from matrix)

B1 (substrate eligibility) **stays OPEN** — upgraded
`OPEN_REQUIRES_M3 → OPEN_REQUIRES_M4`.

**Closure rule** (verbatim from protocol §B1):

> B1 moves to `CLOSED_FOR_ELIGIBILITY_ONLY` IFF:
> 1. all 3 prereg-scoped substrates have ≥1 ELIGIBLE null strategy
> 2. each strategy has deterministic same-seed replay
> 3. each preserves topology semantics within locked tolerances
> 4. each has non-degenerate null contrast
> 5. all fail-closed adversarial traps pass
> 6. no claim-boundary violation
> 7. D002C ledger byte-exact unchanged
> 8. B2 still represented as SEPARATE open blocker
>
> Canonical run remains BLOCKED unless B1 closes AND B2 closes/accepted
> AND explicit canonical-run authorisation artifact exists — NONE of
> which this PR creates.

On this PR's grid: condition (1) fails for `block_structured` and
`temporal_coupling`. B1 cannot close.

## 13. B2 status

B2 remains **OPEN** (percentile-CI limitation, unchanged from prior PRs).
This PR does NOT touch B2 in any way. The §B2 subsection of
`D002G_CANONICAL_RUN_BLOCKERS.md` is read-only here.

## 14. Canonical-run status

**BLOCKED**. The canonical-run authorisation AND-conjunction requires
B1 closure ∧ B2 closure ∧ explicit canonical-run authorisation artifact.
NONE of those conjuncts are satisfied by this PR. No canonical run is
launched, authorised, or implicitly enabled by M3 eligibility on
`ricci_flow` alone.

## 15. D002C ledger status

**UNTOUCHED**. `docs/governance/D002C_CLAIM_LEDGER.yaml` sha256 pin:
`f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd`.
Verified byte-exact via
`tests/systemic_risk/test_d002g_m3_invariants.py::test_m3_inv_8_d002c_claim_ledger_unchanged`
and
`tests/systemic_risk/test_d002g_m3_no_promotion.py::test_m3_d002c_ledger_sha256_unchanged`.

## 16. Claim boundary (verbatim)

> This PR implements M3 null-admissibility infrastructure only. It
> does NOT establish D-002G scientific PASS. It does NOT authorise
> canonical D-002G run. It does NOT close B2. It does NOT update
> D002C_CLAIM_LEDGER.yaml. M3 eligibility alone is not canonical-run
> authorisation.

## 17. Exact test commands

```
PYTHONPATH=. python -m pytest \
  tests/systemic_risk/test_d002g_m3_verdicts.py \
  tests/systemic_risk/test_d002g_m3_invariants.py \
  tests/systemic_risk/test_d002g_m3_negative_controls.py \
  tests/systemic_risk/test_d002g_m3_traps.py \
  tests/systemic_risk/test_d002g_m3_no_promotion.py \
  -q
```

Regression sweep (P1 / P2 / P3 + M3 together):

```
PYTHONPATH=. python -m pytest tests/systemic_risk/ -k \
  "d002g or d002c or m3 or p3 or m2" -q
```

Matrix regeneration:

```
PYTHONPATH=. python scripts/x10r_d002g_m3_eligibility_matrix.py
```

## 18. Exact test results

Counts at PR head (see CI artifacts for the canonical-run record):

* `test_d002g_m3_verdicts.py` — 6 tests, all PASS.
* `test_d002g_m3_invariants.py` — 13 tests (M3-INV-1 .. M3-INV-8 + ancillary
  salt / constant locks), all PASS.
* `test_d002g_m3_negative_controls.py` — 4 tests (NC-M3-1..4), all PASS.
* `test_d002g_m3_traps.py` — 12 tests (T1..T10 + bonus), all PASS.
* `test_d002g_m3_no_promotion.py` — 4 tests, all PASS.

Total M3-suite: **39 tests**, all green.

All prior P1 / P2 / P3 tests remain green and unmodified.

## 19. Remaining blockers

* **B1** — `OPEN_REQUIRES_M4`. Two of three prereg-scoped substrates
  have no ELIGIBLE null strategy across the full M1 ∪ M2 ∪ M3 surface.
* **B2** — OPEN (percentile-CI limitation; untouched in this PR).
* Canonical-run authorisation — BLOCKED. No authorisation artifact
  is issued by this PR; M3 eligibility on `ricci_flow` alone does
  not unblock canonical run scope.

## 20. Next required PR

Given the empirical decision state
**`M3_INELIGIBLE_M4_REQUIRED`**, the next required PR is:

```
feat(x10r,D-002G,M4): pre-registration of <next mechanism family>
```

The author should choose the next mechanism family AFTER reviewing
the M3 INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC root cause: both blocked
substrates have seed-deterministic precursor lifts, so any next
mechanism MUST either (a) introduce substrate-level seed-dependence at
λ > 0 (substrate-API surgery, outside D-002G scope), OR (b) define
its null on a domain that captures the deterministic lift's
information content directly (e.g. analytical-cohort null, model-based
parametric null with explicit prior on lift magnitude). Option (b)
is the protocol-correct path; the implementation PR pre-registers
the M4 family separately and locks at THAT PR's merge commit.

This M3 PR explicitly does NOT pre-register M4. Touching the M3
pre-reg in this PR would constitute a fresh M4 pre-registration, not
an M3 implementation; pre-registration discipline forbids that.

---

**Operating law (verbatim, M3 protocol):** "Your job is not to make
M3 pass. Your job is to discover whether M3 has the right to exist."
The truthful `INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC` verdict on the
two blocked substrates IS the scientific result — a KillArtifact
preserved by the verifier's fail-closed admissibility ladder.
