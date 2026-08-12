# D-002H Gate C — Canonical Parameter Grid (declared, not executed)

**Study:** D-002H
**Gate:** C — canonical parameter grid declared
**Status:** PASS (declaration only — no compute, no sweep, no results)
**Machine artifact:** [`artifacts/d002h/canonical/d002h_canonical_grid.json`](../../artifacts/d002h/canonical/d002h_canonical_grid.json)
**Schema:** `D002H-CANONICAL-GRID-v1`

---

## 1. Scope

This artifact closes Gate C of the locked D-002H authorisation conjunction
described in [`D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md`](D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md) §C.

Gate C is **pure declaration**: it pins, as a content-addressed artifact,
the canonical parameter grid copied byte-equivalent from the
`canonical_grid` block of the locked D-002H pre-registration. Gate C
**does not execute** the canonical run, **does not produce** results, and
**does not authorise** the run. The 7-gate conjunction
A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G is the authorisation contract; this PR
addresses Gate C only.

Gates A and B are already closed on `main`:

| Gate | Artifact | Anchor sha |
|------|----------|------------|
| A    | [`docs/governance/D002H_PREREGISTRATION.yaml`](D002H_PREREGISTRATION.yaml) | `1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5` (PR #683 merge) |
| B    | [`artifacts/d002h/eligibility/d002h_ricci_eligibility.json`](../../artifacts/d002h/eligibility/d002h_ricci_eligibility.json) | `b97daae8b554ab9960510564e19263adcc1fe71b` (PR #684 merge) |

Gates **D, E, F, G** remain open after this PR.

---

## 2. Parent prereg anchor

The grid is content-addressed against the locked D-002H pre-registration:

- **Prereg path:** `docs/governance/D002H_PREREGISTRATION.yaml`
- **Prereg sha256 (locked, PR #683 anchor):**
  `44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec`
- **D-002H lineage parent_closure:** `D-002G_STRUCTURAL_CLOSURE`
  (parent_merge_sha `8cf5364a3f3b605d8b134bccbfe5170098e0e197`, PR #682)

The pre-registration's `canonical_grid` block is the single source of
truth; the JSON artifact carries the same numbers under the
`D002H-CANONICAL-GRID-v1` schema.

---

## 3. Grid table (18 cells, ricci_flow only)

Cell identifier convention: `cell_id = f"ricci_flow_N{N}_lam{lambda}"`,
scope `canonical_d002h`.

| N   | λ    | cell_id                       | scope             |
|-----|------|-------------------------------|-------------------|
| 50  | 0.00 | `ricci_flow_N50_lam0.0`       | `canonical_d002h` |
| 50  | 0.05 | `ricci_flow_N50_lam0.05`      | `canonical_d002h` |
| 50  | 0.10 | `ricci_flow_N50_lam0.1`       | `canonical_d002h` |
| 50  | 0.20 | `ricci_flow_N50_lam0.2`       | `canonical_d002h` |
| 50  | 0.40 | `ricci_flow_N50_lam0.4`       | `canonical_d002h` |
| 50  | 1.00 | `ricci_flow_N50_lam1.0`       | `canonical_d002h` |
| 100 | 0.00 | `ricci_flow_N100_lam0.0`      | `canonical_d002h` |
| 100 | 0.05 | `ricci_flow_N100_lam0.05`     | `canonical_d002h` |
| 100 | 0.10 | `ricci_flow_N100_lam0.1`      | `canonical_d002h` |
| 100 | 0.20 | `ricci_flow_N100_lam0.2`      | `canonical_d002h` |
| 100 | 0.40 | `ricci_flow_N100_lam0.4`      | `canonical_d002h` |
| 100 | 1.00 | `ricci_flow_N100_lam1.0`      | `canonical_d002h` |
| 200 | 0.00 | `ricci_flow_N200_lam0.0`      | `canonical_d002h` |
| 200 | 0.05 | `ricci_flow_N200_lam0.05`     | `canonical_d002h` |
| 200 | 0.10 | `ricci_flow_N200_lam0.1`      | `canonical_d002h` |
| 200 | 0.20 | `ricci_flow_N200_lam0.2`      | `canonical_d002h` |
| 200 | 0.40 | `ricci_flow_N200_lam0.4`      | `canonical_d002h` |
| 200 | 1.00 | `ricci_flow_N200_lam1.0`      | `canonical_d002h` |

Total: **18 cells = 1 substrate × 3 N × 6 λ**. No drift from the prereg.

---

## 4. Sampling parameters (locked)

| Parameter        | Value   | Source field in prereg                 |
|------------------|---------|----------------------------------------|
| `n_seeds`        | `20`    | `canonical_grid.n_seeds`               |
| `n_bootstrap`    | `16`    | `canonical_grid.n_bootstrap`           |
| `base_seed`      | `42`    | grid root (matches Gate B `base_seed`) |
| `null_seed_M3`   | `12345` | `reproducibility.null_seed_M3`         |

These are pinned in the machine artifact and the Gate C tests assert
each against the prereg verbatim, with negative-case drift sentinels
(Lesson 4) for the common defaults `{1, 5, 10, 50, 100}` and
`{1, 100, 1000}`.

---

## 5. Claim boundary (verbatim)

> Gate C declares the canonical parameter grid for D-002H. It does
> NOT authorise canonical run. It does NOT execute any sweep. It does
> NOT produce results. The 7-gate conjunction
> A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G is the canonical-run authorisation
> contract; this PR addresses Gate C only.

---

## 6. Forbidden interpretations

- ❌ "Gate C means the canonical run has started." It has not.
- ❌ "Gate C results are sweep results." No results exist.
- ❌ "Gate C extends to block_structured or temporal_coupling."
  Substrate scope is `ricci_flow` only per D-002H prereg
  (`substrate_scope.excluded = [block_structured, temporal_coupling]`,
  exclusion reasons recorded in the prereg).
- ❌ "Gate C authorises D-002G or D-002C rescue." It does not; D-002G
  closed structurally per PR #682.
- ❌ "Gate C is a scientific PASS." It is a declaration, not evidence.

---

## 7. Reproduce

```bash
# Re-verify the locked prereg sha (Gate A anchor)
test "$(sha256sum docs/governance/D002H_PREREGISTRATION.yaml | awk '{print $1}')" \
  = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"

# Re-verify the D-002C ledger sha (cross-study invariant)
test "$(sha256sum docs/governance/D002C_CLAIM_LEDGER.yaml | awk '{print $1}')" \
  = "f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd"

# Verify the grid JSON parses and matches the prereg byte-equivalent
PYTHONPATH=. python -c "
import json, yaml
g = json.load(open('artifacts/d002h/canonical/d002h_canonical_grid.json'))
p = yaml.safe_load(open('docs/governance/D002H_PREREGISTRATION.yaml'))
cg = p['canonical_grid']
assert g['substrates']    == cg['substrates']
assert g['N']             == cg['N']
assert g['lambda_values'] == cg['lambda_values']
assert g['n_seeds']       == cg['n_seeds']
assert g['n_bootstrap']   == cg['n_bootstrap']
assert g['total_cells']   == cg['total_cells']
print('GRID_VS_PREREG_CONSISTENT')
"

# Run the Gate C invariant tests
PYTHONPATH=. python -m pytest tests/systemic_risk/test_d002h_gate_c_grid.py -q
```

Gate C PASS is a necessary term in the conjunction; canonical run remains
**BLOCKED** until Gates D, E, F, G additionally PASS in their own
downstream artifacts.
