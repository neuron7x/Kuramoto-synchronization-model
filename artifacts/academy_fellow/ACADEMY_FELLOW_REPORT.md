# Academy-Fellow Physics × Neuroscience Witness Hardening

Closes the witness gap declared by `.claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml`:
every mechanism that carried an open `missing_tests` / `remediation_action` now has a
dedicated, formula-derived, falsifier-bearing witness test. **No new physics, no new
solver, no new neuroscience** — existing mechanisms only.

## What landed

- **13 witness tests** (12 unit + 1 integration), all tolerances formula-derived
  (no magic numbers), each with an explicit engineering-analog NON-CLAIM.
- **Ledger reconciliation**: `missing_tests` → `existing_tests` across 13 entries;
  **no** claim-tier promotions. An initial promotion of 4 PARTIAL→OPERATIONAL
  (dopamine adapter, neuro-optimizer null model, hebbian, homeostatic) was
  **rejected by the repo's own neuro audit** (`tools/audit/neuro_symbolic_audit.py`):
  OPERATIONAL requires ≥1 `INV-*` binding and these have none. Reverted to PARTIAL —
  witness admissible, promotion blocked on defining the invariant (admissibility ≠ promotion).
- **Final ledger: 18 OPERATIONAL / 6 PARTIAL** (every PARTIAL with an active
  non-KEEP remediation); 0 open `missing_tests`. The 6 PARTIAL:
  `neuro-validation-bounds` (QUARANTINE_DOC), `coherence-bridge-geosync-adapter`
  (open fail-closed gap on out-of-band negative gamma), and the 4 above.
- **`scripts/ci/check_neuro_claim_boundary.py`**: fail-closed gate against
  biological-equivalence overclaim in runtime source (0 violations today; falsifier-verified).
- **`scripts/ci/gen_law_mechanism_witness_matrix.py`** → machine-readable
  `law_mechanism_witness_matrix.json` + `traceability_report.json`.

## Honest findings (not masked)

- **Pre-existing, out-of-scope**: `tests/unit/physics/test_T28_wave2_witnesses.py::
  test_ott_antonsen_unit_disk_bound_property` fails on a Hypothesis counterexample at
  `core/kuramoto/ott_antonsen.py:329` (steady-state stalls at the unstable fixed point for
  vanishing R0). Reproduces on the clean base with all new files removed.
- **`adaptive-criticality-kappa`**: the κ_critical / isolation gate is a *documented
  derivation* (CLAUDE.md + INV-AC1-rev), not executed source; the witness anchors the
  closed form to the real `DFAGammaEstimator` λ output.
- **`coherence-bridge`**: exposed `ricci_curvature` is an augmented-Forman blend
  (legitimately > 1), not the Ollivier κ ≤ 1 field — RC1 asserted on the Ollivier operator;
  adapter relays out-of-band negative gamma without failing closed.

## NON-CLAIMS

No biological equivalence. No universal physics of markets. No alpha/profitability.
No real L2 validation (synthetic-only witnesses). "Academy-Fellow" denotes artifact
discipline, not a status claim.
