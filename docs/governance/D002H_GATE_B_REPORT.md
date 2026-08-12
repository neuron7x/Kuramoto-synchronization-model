# D-002H Gate B Report — ricci_flow M1/M3 Eligibility Reverification

## 1. Scope

This report documents Gate B of the 7-gate canonical-run authorisation
conjunction defined in
[`D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md`](D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md).
Gate B reverifies that the `ricci_flow` substrate is M1- and M3-eligible
at the locked D-002H canonical grid AT THIS COMMIT.

The verifiers `verify_m3_eligibility` (and the M1 admissibility contract
encoded inside `_realize_m1`) are reused verbatim from
`research/systemic_risk/d002g_null_mechanisms.py`; they were sha-pinned at
the M1/M3 merges (PR #677 / PR #681). This PR introduces NO new mechanism,
NO new verdict literal, NO new salt, NO new tolerance constant, and NO
substrate or mechanism code edit.

## 2. Pre-Registration Anchor

* **D-002H pre-registration:** `docs/governance/D002H_PREREGISTRATION.yaml`
  (schema `D002H-PREREGISTRATION-v1`).
* **Parent merge sha (Gate A):** `1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5`
  (PR #683 — D-002H prereg lock on `origin/main`).
* **D-002G structural closure parent:**
  `8cf5364a3f3b605d8b134bccbfe5170098e0e197` (PR #682).
* **D-002C claim ledger sha256 (verified byte-exact UNCHANGED):**
  `f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd`.

## 3. Method

* **Script:** `scripts/x10r_d002h_gate_b_eligibility.py`.
* **Invocation:**
  ```
  PYTHONPATH=. python scripts/x10r_d002h_gate_b_eligibility.py
  ```
* **Deterministic seeding contract:** reused verbatim from
  `research/systemic_risk/d002g_null_mechanisms.py`.
  - M1 null seed: `base_seed + NULL_SEED_OFFSET` where
    `NULL_SEED_OFFSET == 10000` (locked at the M1 merge).
  - M3 null seed: `null_seed_M3 == 12345` (locked at the M3 merge).
  - M3 salt: `M3_TOPOLOGY_CONDITIONED_SALT == 523` (locked at the M3 merge).
  - All randomness routed through `np.random.default_rng(seed)`; no
    global RNG, no time-based seed, no `import random`.
* **M1 evaluation method.** There is no public `verify_m1_eligibility`
  symbol in the M1 module. The M1 admissibility contract is encoded
  inside `_realize_m1`: a cell is M1-ELIGIBLE iff
  `realize_null(strategy="M1_INDEPENDENT_SEED", ...)` succeeds; the
  module raises `BitIdenticalNullError` when the substrate is
  seed-insensitive at the cell, with the documented fail-closed
  literal `INELIGIBLE_M1_BIT_IDENTICAL`. The script invokes
  `realize_null` and translates the outcome into `ELIGIBLE_M1` /
  `INELIGIBLE_M1_BIT_IDENTICAL` / `INDETERMINATE_M1_PROVENANCE_MISSING`
  without coining any new verdict literal.
* **M3 evaluation method.** Direct invocation of
  `verify_m3_eligibility` with the locked seeds. The module's contract
  refuses `lambda_value <= 0` by raising `D002GNullInvalid`; cells with
  `lambda_value == 0.0` are therefore reported as
  `N/A_M3_REQUIRES_LAMBDA_GT_ZERO` per the M3 module's contract.
* **Cell-level Gate B pass rule.**
  `m1_status == "ELIGIBLE_M1"` AND
  (`m3_status == "ELIGIBLE_M3"` OR `m3_status == "N/A_M3_REQUIRES_LAMBDA_GT_ZERO"`).
* **Gate B verdict rule.** PASS iff every cell passes; otherwise FAIL.
  FAIL halts downstream gates; the verdict is the truth and is not
  forced.

## 4. Verdict Matrix (18 cells = 3 N × 6 λ)

| N   | λ    | M1 status     | M3 status                              | cell PASS |
|-----|------|---------------|----------------------------------------|-----------|
|  50 | 0.00 | ELIGIBLE_M1   | N/A_M3_REQUIRES_LAMBDA_GT_ZERO         | YES       |
|  50 | 0.05 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
|  50 | 0.10 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
|  50 | 0.20 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
|  50 | 0.40 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
|  50 | 1.00 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 100 | 0.00 | ELIGIBLE_M1   | N/A_M3_REQUIRES_LAMBDA_GT_ZERO         | YES       |
| 100 | 0.05 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 100 | 0.10 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 100 | 0.20 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 100 | 0.40 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 100 | 1.00 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 200 | 0.00 | ELIGIBLE_M1   | N/A_M3_REQUIRES_LAMBDA_GT_ZERO         | YES       |
| 200 | 0.05 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 200 | 0.10 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 200 | 0.20 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 200 | 0.40 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |
| 200 | 1.00 | ELIGIBLE_M1   | ELIGIBLE_M3                            | YES       |

Full machine-readable artifact:
`artifacts/d002h/eligibility/d002h_ricci_eligibility.json`
(schema `D002H-GATE-B-v1`).

## 5. Gate B Verdict — PASS

**`gate_b_verdict: PASS`** (18/18 cells PASS).

Interpretation: ricci_flow is M1- and M3-eligible at every cell of the
locked D-002H canonical grid `{N=50,100,200} × λ ∈ {0.0, 0.05, 0.10,
0.20, 0.40, 1.0}` AT THIS COMMIT. At λ=0 the M3 verifier returns N/A
by construction (its contract refuses `lambda_value <= 0`); M1 is
evaluable at λ=0 and returns `ELIGIBLE_M1` on every cell. At every
λ>0 cell the M3 verifier returns `ELIGIBLE_M3` with the marginal-match
report inside the locked tolerances. No cell required the
`INELIGIBLE_M1_BIT_IDENTICAL` or any `INELIGIBLE_M3_*` literal.

## 6. Claim Boundary (verbatim)

> Gate B PASS certifies that ricci_flow is M1- and M3-eligible at the
> locked canonical grid AT THIS COMMIT. It does NOT authorise canonical
> run. The 7-gate conjunction A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G is the
> authorisation contract; this PR addresses Gate B only. Gates C, D, E,
> F, G remain open.

## 7. Forbidden Interpretations

- ❌ "Gate B PASS authorises canonical run." It does not. Only the
  conjunction A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G does.
- ❌ "Gate B verifies block_structured or temporal_coupling." It does
  not — those substrates are explicitly excluded per the D-002H
  pre-registration scope and the D-002G structural-closure verdict.
- ❌ "Gate B replaces or supersedes any prior D-002G eligibility
  verdict." Prior D-002G verdicts remain sha-pinned in their respective
  merges and are unaffected by this PR.
- ❌ "Gate B rescues D-002G or D-002C." It does not. D-002H is a fresh
  pre-registered lineage; D-002G remains structurally closed.
- ❌ "Gate B implies cross-substrate robustness or general topology
  robustness." It does not — by D-002H pre-registration scope, this
  Gate covers ricci_flow only.

## 8. Reproduce

```
PYTHONPATH=. python scripts/x10r_d002h_gate_b_eligibility.py
```

Expected: exit code `0`, artifact written to
`artifacts/d002h/eligibility/d002h_ricci_eligibility.json`,
`gate_b_verdict == "PASS"` with `n_cells_pass == 18`.

## 9. Next Gate

Gate C (canonical parameter grid declared) — emits
`artifacts/d002h/canonical/d002h_canonical_grid.json` in a SEPARATE PR.
Gates D, E, F, G follow per
[`D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md`](D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md).
Canonical D-002H run remains BLOCKED.
