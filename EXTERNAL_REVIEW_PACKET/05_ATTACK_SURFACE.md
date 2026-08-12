# Attack Surface

> Where an adversary tries to make the instrument lie. Each row is
> a known attack vector with its current defence.

| # | Attack vector | Defender | Defence |
|---|---|---|---|
| A1 | Inject future data into the score builder | `leakage_sentinel.check_future_data_via_mutation` | mutation-test invariant: past score must not change when future is overwritten |
| A2 | Hide a label-leakage column in the panel | `data_firewall.gate_*` schema check + `leakage_sentinel.check_label_leakage` | enumerated forbidden columns + op-graph backwards-edge detection |
| A3 | Centred rolling window posing as trailing | `leakage_sentinel.check_centered_windows` | config-key sweep against `_FORBIDDEN_CENTERED_KEYS` |
| A4 | Full-sample normalization smuggled into op-log | `leakage_sentinel.check_full_sample_normalisation` | op-log scan against `_FORBIDDEN_FULL_SAMPLE_OPS` |
| A5 | Crisis-date tuning after seeing AUC | `leakage_sentinel.check_crisis_date_tuning` | `crisis_lock_timestamp_utc < first_evaluation_timestamp_utc` enforced |
| A6 | Post-event window contamination | `leakage_sentinel.check_post_event_contamination` | `min_lead_time ≥ 1` floor |
| A7 | Survivorship bias (only-survived banks in the universe) | `data_firewall.gate_provenance` + node-mapping uniqueness | `node_mapping.bank_label.duplicated()` rejected |
| A8 | License/regulation block bypass | `data_firewall.gate_provenance` (X-9R: `license.txt` BLOCKED-token check) | structured BLOCKED verdict, not silent crash |
| A9 | Bootstrap CI gaming via tiny n | `falsification.auc_bootstrap_ci` + Bonferroni | n ≥ 3 events required for FWER α=0.01 |
| A10 | AUC-only reporting (suppressing CI / p-value) | `protocol_x9r._gate_metrics_validity` | required-key check on metrics dict |
| A11 | Replication mismatch hidden by close-enough tolerance | `replication_capsule.compare_run_outputs` | tolerance class is pre-registered; `stochastic_seeded` requires explicit override |
| A12 | Resurrect a REJECTED claim | `governance_fsm.GovernanceFSM.apply` | REJECTED is absorbing; metamorphic test pinned |
| A13 | Promote claim through evidence overstatement | `governance.run_premerge_science_gate` | overclaim grep + readiness profile cap |
| A14 | Public API drift / orphan symbols | `tools/check_public_symbol_matrix.py` | matrix CSV + audit tool |
| A15 | Floating claims in user-facing docs | `tools/compile_claims.py --fail-on-floating` | every claim must have ≥ 1 evidence anchor + ≥ 1 falsifier |
| A16 | Tampered capsule (edited `metrics_sha`) | `protocol_x9r._gate_rerun_check_during_rerun` | RERUN_CHECK FAIL → REJECTED (terminal) |

## Out-of-scope (deliberately undefended)

* Compromise of the local Python interpreter or numpy/scipy
  dependencies. We trust the SBOM lockfile and the GitHub
  Dependabot upgrades.
* Compromise of git itself (commit-sha forgery). We trust SHA-256.
