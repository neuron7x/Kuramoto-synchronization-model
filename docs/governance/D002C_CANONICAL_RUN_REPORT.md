# D-002C Canonical Synthetic Run Report

## 1. Run Identity

- **Run class:** `D002C_CANONICAL_SYNTHETIC_SWEEP_ATTEMPT_1`
- **RUN_DIR:** `tmp/d002c_canonical_20260512T122837Z`
- **Exit code:** `0`
- **Tier:** `SYNTHETIC_GATE6_CERTIFIED_REDESIGN_N_LE_200`
- **Wallclock:** 152.4s (E-core throttled, single-thread BLAS, nice 10)
- **Hardware envelope at run:** Package 45–58°C, RAM 1.8–4.0 GiB available, load avg 1.6–2.0

## 2. Verdict Summary

- **selected_cell_key:** `[100, 0.05, "block_structured", "sync_auc"]`
- **n_cells_evaluated:** 45 (λ > 0 cells after preflight exclusions)
- **n_cells_passing:** 45 / 45
- **marginal_pass:** `false`
- **single_path_pass:** `false`
- **Passing substrate × metric scope:**
  - `block_structured × sync_auc`
  - `ricci_flow × sync_auc`
  - `temporal_coupling × sync_auc`

## 3. Cryptographic Anchors

| Anchor | sha256 |
|---|---|
| preregistration_sha | `b1561ddde08a60a8eed416f2103655e0f3ee1ecd4e2b2037f4e7193c424a154e` |
| preflight_decision_sha | `a065d18223b9cd126c6839990e0877b436198c2424c771d09323b8fa30266a40` |
| sweep_sha | `54b1dd9d8059197f3463b9728d54adb632ec45b2459bcae001a08efe4dee2b16` |
| verdict_sha | `9380bb42db9e858e759ffacfd1906cd54023cae24e3d72ef83d1df8b8dbc9bd5` |
| archive_sha256 | `c4f62f867f4aee6bb17ab6c768a6faf3791f2fedf17bd576490a2bb499566e1d` |

Per-capsule sha (preflight integrity):

```
pos_control.json   4de86ed462b77f4bd23fb8b04de276682877315a5b2861f3d6ee34d1a0470bb5
neg_control.json   2d1f60008ac7624bb43cd098df489e3d6e0e754a9c9a58f2689460e69267d9fb
smoke_test.json    927950f3a408c76666cd6409c0d3d0055a791a8e2761df4f9f629c7136354a6a
null_audit.json    3376df404d3cd8fcb27ee7d358c31485615302389283e656186f871dd1f4c3dd
```

## 4. Acceptance Rule

D-002C passed the locked pre-registered R1 ∧ R2 ∧ R3 synthetic acceptance rule
at the selected cell:

| Rule | Threshold | Measured at selected cell | Passed |
|---|---|---|---|
| R1: \|signal_mean\| / CI_half_width | > 1.0 | 5.47 | ✓ |
| R2: FPR(λ=0) | ≤ 0.05 | 0.00 | ✓ (see §7.2) |
| R3: direction stability | ≥ 0.80 | 1.00 | ✓ |

ALL 45 evaluated cells (λ > 0) passed R1 ∧ R2 ∧ R3.

## 5. Scope

**Supported:**
- synthetic-only
- `sync_auc` metric
- three synthetic substrate families (ricci_flow, block_structured, temporal_coupling)
- N ∈ {50, 100, 200}
- surviving pre-registered grid after preflight exclusions

**Not supported by this verdict:**
- real-data validation
- bank-level inference
- production readiness
- universal claim
- `tau_onset` claim (excluded by POS preflight)
- `phase_lag` claim (excluded by POS preflight)

## 6. Preflight Effects

POS preflight (N=400, λ=1.0, n_seeds=50, signal_ci_ratio > 2.0 required):

| substrate × metric combo | result |
|---|---|
| 3 substrates × `sync_auc` | 3 PASS |
| 3 substrates × `tau_onset` | 3 EXCLUDE |
| 3 substrates × `phase_lag` | 3 EXCLUDE |

NEG preflight (λ=0, FPR ≤ α_bonferroni + 1e-3):

| excluded cells |
|---|
| `ricci_flow × tau_onset × N=50` |
| `ricci_flow × phase_lag × N=50` |
| `temporal_coupling × tau_onset × N=50` |
| `temporal_coupling × phase_lag × N=50` |

(All 4 NEG-excluded cells are already POS-excluded combos; net additional exclusions = 0.)

Surviving scientific scope after preflight:
`sync_auc × {ricci_flow, block_structured, temporal_coupling} × N ∈ {50, 100, 200}`

## 7. Known Gaps

### 7.1 Null-audit execution gap

`research.systemic_risk.d002c_null_audit.run_null_audit_all` exists (merged via
PR #672 / C2.4-C2), but `research.systemic_risk.d002c_sweep_runner` does not
yet persist per-seed precursor and null paired sample VALUES into the
checkpoint or output. Therefore the null-audit safeguard was NOT exercised
on this canonical run.

Pre-sweep `null_audit.json` carried `aggregate_only=true` with empty `results`
(the correct pre-sweep state — there is nothing to audit before the sweep runs).
Post-sweep, an attempt to invoke `run_null_audit_all(sweep_capsule_path=ckpt)`
was made and refused with `NullAuditAggregateInvalid: resolved cell list is
empty`. Documented in `tmp/d002c_canonical_20260512T122837Z/evidence/NULL_AUDIT_GAP_NOTE.md`
and `evidence/null_audit_attempt.txt`.

**Required follow-up:** C2.4-A2 must extend `sweep_runner` /
`sweep_checkpoint` schema to persist per-seed paired values. Spec in
`docs/governance/D002C_NULL_AUDIT_GAP_AND_C2_4_A2_SPEC.md`.

### 7.2 R2 structural limitation

At λ=0 under paired CRN, `K_precursor == K_baseline` bitwise (by construction —
no precursor injection at λ=0). Therefore the metric difference is exactly
zero per seed, `signal_mean = 0`, BCa CI half-width is tiny, and
`signal_over_ci → 0`. R2's FPR estimator returns 0.00 across all swept null
cells of the selected (substrate, metric, N).

R2 is mechanically satisfied under the current paired-CRN implementation
and has limited evidential strength as an independent false-positive
safeguard until redesigned or supplemented. Detailed note:
`docs/governance/D002C_R2_STRUCTURAL_LIMITATION_NOTE.md`.

## 8. Claim Boundary

D-002C produced a **canonical synthetic PASS** under the locked
pre-registered acceptance rule (R1 ∧ R2 ∧ R3) for the `sync_auc` metric
across three synthetic substrate families at N ∈ {50, 100, 200}.

**No real-data, bank-level, production, universal, or external
certification claim is made by this run.** The null-audit safeguard is a
known structural gap pending C2.4-A2; R2 has the structural limitation
described in §7.2.

## 9. Next Required Work

| Priority | Item |
|---|---|
| P0 | **This freeze PR** (current) |
| P1 | C2.4-A2: persist per-seed precursor/null paired values into sweep_runner + checkpoint |
| P2 | Post-C2.4-A2 canonical rerun (new RUN_ID, real null_audit executed) |
| P3 | R2 redesign or supplementary null rule (separate research thread, not D-002C launch blocker) |
| P4 | #670 Clock DI reliability hardening (independent reliability PR; not D-002C blocker) |
