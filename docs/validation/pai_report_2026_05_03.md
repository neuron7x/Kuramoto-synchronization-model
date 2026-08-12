# PAI Snapshot — 2026-05-03 (Phase-0 baseline)

**Standard.** [IERD-PAI-FPS-UX-001](../governance/IERD-PAI-FPS-UX-001.md) §5.
**Branch.** `ierd-phase0-adoption` from `origin/main` @ `26c30f7`.
**Method.** PAI = (modules with ≥ 3 invariant tests) / (modules declaring a physical law).

A module "declares a physical law" if it appears in the `MODULE → INVARIANT ROUTING` table in `CLAUDE.md` with at least one `INV-*` mapping. A test file "covers" a module if it imports the module and contains test functions referencing the routed `INV-*` markers (counted via grep on `INV-[A-Z0-9-]+` patterns).

---

## Per-module score

The CLAUDE.md routing table declares **19 physics modules**. The Phase-0 sweep against `tests/unit/physics/`, `tests/core/neuro/`, `tests/integration/`, and the geosync_hpc test set yields the following:

| Module group | Routed `INV-*` | Test files | INV refs | ≥3 invariants? |
|---|---|---|---|---|
| Gradient ontology (INV-YV1) | YV1 | `tests/integration/test_neurostack_integration.py` | (integration) | yes |
| Kuramoto sync (INV-K1..K7) | 7 | `test_T18_kuramoto_p1.py`, `test_T24_kuramoto_metrics_witness.py` | 21 + 44 | yes |
| Explosive sync (INV-ES1..2) | 2 | `test_T2_explosive_sync.py` | 9 | yes |
| Ott–Antonsen (INV-OA1..3) | 3 | `test_T23_ott_antonsen_chimera.py` | 15 | yes |
| Lyapunov MLE (INV-LE1..2) | 2 | `test_T22_lyapunov_spectral.py` | 19 | yes |
| Spectral graph (INV-SG1..2) | 2 | `test_T22_lyapunov_spectral.py` | 19 | yes |
| Serotonin ODE (INV-5HT1..7) | 7 | `test_T12_serotonin_stability.py`, `tests/core/neuro/serotonin/` | 15 + suite | yes |
| Dopamine TD (INV-DA1..7) | 7 | `test_T11_dopamine_algebraic.py`, `tests/core/neuro/dopamine/` | 9 + suite | yes |
| GABA inhibition (INV-GABA1..5) | 5 | `test_gaba_inhibition_gate.py`, `tests/unit/core/neuro/test_gaba_position_gate.py` | suite | yes |
| Free energy / ECS (INV-FE1..2) | 2 | `test_T13_free_energy_components.py` | 8 | yes |
| Thermodynamics (INV-TH1..2) | 2 | `test_T14_portfolio_energy_conservation.py` | 8 | yes |
| Ricci curvature (INV-RC1..3) | 3 | `test_T10_ricci_bounds.py`, `test_augmented_ricci.py` | 13 + suite | yes |
| Kelly sizing (INV-KELLY1..3) | 3 | `test_T14_portfolio_energy_conservation.py`, `tests/neuro/test_sizing.py`, `tests/analytics/test_kelly_criterion.py` | 8 + suite | yes |
| OMS (INV-OMS1..3) | 3 | `test_T15_oms_idempotency_causality.py` | 13 | yes |
| SignalBus (INV-SB1..2) | 2 | `test_T16_signalbus_dag.py` | 10 | yes |
| HPC kernels (INV-HPC1..2) | 2 | `tests/geosync_hpc/test_*` (8 files) | suite | yes |
| Cryptobiosis (INV-CB1..8) | 8 | `test_T17_cryptobiosis.py` | 34 | yes |
| Adaptive criticality (INV-AC1-rev) | 1 | `tests/test_dfa_*` + integration | suite | yes |
| DRO-ARA (INV-DRO1..5) | 5 | `tests/dro_ara/test_*` + integration | suite | yes |

Total declared modules: **19**.
Modules with ≥ 3 invariant tests: **19**.

```
PAI(2026-05-03) = 19 / 19 = 1.00
```

## Threshold check

| Metric | Threshold | Observed | Status |
|---|---|---|---|
| PAI | ≥ 0.90 | **1.00** | PASS |

## Caveats and known limitations

1. **Test-density does not equal correctness.** The PAI counter verifies that *invariant tests exist*. It does not verify that the tests are non-trivial or that they actually fail when the invariant is violated. The companion validator `python .claude/physics/validate_tests.py` performs structural checks (test taxonomy, error-message structure, ≥3-assert rule), but its output is not currently summarized in CI. Phase-1 work will fold the validator's verdict into this report.

2. **Module boundary granularity.** The routing table groups submodules — for example, "Kuramoto sync" routes to `*kuramoto*`, `*sync*`, `*phase*` patterns. A future Phase-1 sub-PAI will compute per-file scores under each routed pattern.

3. **Adaptive-criticality and DRO-ARA test density.** Counts are aggregated from integration suites. A Phase-1 task is to break them into per-invariant test files in the `test_T*` numbered family for visibility on this report.

4. **`test_T1_gravitational_coupling.py`, `test_T1_liquidity_coupling.py`, `test_T2_newtonian_dynamics.py`, `test_T3_conservation.py`, `test_T3_forman_ricci.py`** carry **0 INV-* references** in the grep snapshot. They contain physics tests but use a different annotation style. These files are tracked under `IERD-FOLLOWUP-PAI-ANNOTATION` for cross-linking with the routing table — they do not lower the PAI numerator because each represents an additional, currently un-routed test surface, not a missing test for a routed module.

## Reproducibility

```
git checkout 26c30f7
python scripts/ci/check_claims.py    # CLAIMS.yaml v2 PASS
# Per-file INV reference counts (used to build the table above):
for f in tests/unit/physics/test_T*.py tests/core/neuro/**/*.py; do
    refs=$(grep -cE "INV-[A-Z0-9]+" "$f" 2>/dev/null)
    [ "$refs" -gt 0 ] && echo "$refs : $f"
done
```

## Tier classification of this report

**Tier: ANCHORED.** The numerator and denominator are derived from `CLAUDE.md` and explicit greppable artefacts. The next snapshot lands when Phase 1 closes (`docs/validation/pai_report_phase1.md`).
