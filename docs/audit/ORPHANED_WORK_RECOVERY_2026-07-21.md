# Orphaned-Work Recovery & Exposed-Defect Ledger — 2026-07-21

## Context
The canonical gitlab line `grp/main` is a **re-rooted line** (root `8891539a1`) with
**zero shared history** with the pre-migration local branches (root `c7f08bf4c`).
A forensic **content** audit (blob- and path-level, history-independent) proved that
`grp/main` was **missing 113 valid source files** that existed only on branches orphaned
at the 2026-07-17 migration — chiefly `chore/neuro-hardening`, which was marked
"ready to PR" but never merged.

Classification of the 113 (evidence-backed, per file): **68 PORT_NOVEL / 15 SUPERSEDED / 30 INAPPLICABLE**.

## Recovered onto main (verified GREEN, additive — zero edits to existing main files)
### Tier 1 — safety gates (`cbe35ce00`)
- `check_attribute_existence` — a name that resolves to nothing must not guard an action
- `check_silent_procedures` — a failure that reports nothing did not happen (fail-open guard)
- `check_assertion_free_tests` — ratchet vs a test that asserts nothing
- `check_doc_commands` — documented commands must be runnable
- `canonical_counts` — single-source count reconciliation
- Baselines frozen to main's current state; +3 green pytest gates.

### Tier 2 — research protocols + tooling (`a54befc92`)
- `research/real_data/rd_grid_002{,_confirm,_l2}.py`, `rd_l2_003.py`, `rd_ricci_001.py`
- `src/reference/confidence_sequence_reference.py`
- `tools/market_data/binance_{book,depth}_ingest.py`
- Import-clean against main's `research.kernels.*`.

## Latent main defects EXPOSED by the recovered gates (require follow-up remediation)
These are real fail-open / vacuous-governance holes in the canonical line. Not fixed here
(each changes governance semantics and deserves a reviewed PR); recorded for prioritization.

1. **Dangling connectome import-roots** — `docs/architecture/connectome.yaml` declares
   top-level roots `geosync/data`, `geosync/policy/policy_engine`, `geosync/policy/basal_ganglia`
   that do not exist (the code moved to `src/geosync/...`; stale top-level duplicates remain).
   A contract keyed on a non-existent root enforces nothing. `check_config_references` RED.
2. **Gates that do not import standalone** — `scripts/check_dopamine_contract.py`,
   `check_invariant_count_sync.py`, `check_l2_collector_health.py`,
   `scripts/ci/check_physics_inference_readiness.py` import project packages without a
   sys.path bootstrap; they only run under a preset PYTHONPATH. `test_gate_standalone_import` RED.
   (A naive repo-root `insert(0,...)` shadows numpy — the fix must `append`, and be verified
   per-gate against subprocess flakiness.)
3. **Vacuous coverage surfaces** — `configs/quality/coverage_targets.toml` declares surfaces
   `ingestion` (`ingestion/`, `data/`, `core/data/`) and `risk` (`risk/`, `execution/risk`,
   `core/risk`) whose paths do not exist in main. A floor over an empty set is satisfied
   vacuously — the **critical** risk surface governs nothing. Real risk code lives at
   `geosync/risk/`, `runtime/`, `execution/oms.py`. `test_coverage_surface_paths_exist` RED.

The three gates that expose these (`check_config_references`, `test_gate_standalone_import`,
`test_coverage_surface_paths_exist`) are held out of the green tier and preserved in the
recovery bundle; land them once the underlying defects are fixed.

## Deferred / not ported (honest boundary)
- **Reviewer-authority subsystem** (`prospective_*`, `review_calibration`, `ESTIMAND_SPECIFICATION.yaml`,
  `PREREGISTRATION_reviewer_*.yaml`): inert without a reviewer-authority runtime that main lacks.
  Porting the scripts alone yields dead code — needs the whole subsystem or nothing.
- **DSR honest-trial-ledger**: acceptor + test inert without the `robustness.py` TrialLedger change.
- **Exec/risk safety tests** (kill-switch/OMS, 15 files): bound to the abandoned `geosync.*`
  module topology (`geosync.core.security.tls`, `geosync.runtime.kill_switch`) that main
  replaced; main already carries parallel fail-closed coverage
  (`test_kill_switch_controller`, `test_oms_notional_fail_closed`, `test_fail_closed_connectors`).
  SUPERSEDED-in-practice.

## Provenance
Full local history (243 branches + clone lines) preserved at
`~/Downloads/GeoSync-ALL-LOCAL-HISTORY-2026-07-21.bundle` (155M). Classification run
`wf_2b24f7cc-738`. Nothing deleted before this bundle.
