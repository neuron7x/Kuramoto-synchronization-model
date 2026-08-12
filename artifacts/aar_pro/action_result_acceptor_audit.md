# AAR-PRO-V1 Action Result Acceptor Audit

## Claim

AAR-PRO-V1 removes post-factum default prediction synthesis and binds action-result acceptance to deterministic expected/observed comparison with fail-closed chronology and energy breakers.

## Applied invariants

- `AARTracker.record_outcome()` fails closed when no sealed prediction exists for the action.
- `ActionResultComparator` exposes a stateless façade plus `compare_action_result()` alias, marks invalid comparator input as rollback-required, treats metric drift as accepted-but-not-dissolved `UPDATE_REQUIRED`, and uses unnormalised inverse-variance precision distance: `sqrt(sum(diff_i^2 / (variance_i + 1e-9)))`.
- `seal_action_result_evidence()` produces a deterministic SHA-256 replay envelope that binds the expected model, observed afferentation, and witness; stale or forged witnesses are rejected before evidence is emitted.
- `scripts/aar_pro_smoke.py` is the one-command operational smoke: it builds a sealed prediction, sanctions the exact observed result, anchors a seven-phase episode, verifies the hash chain, emits deterministic JSON, and includes the self-healing recovery action.
- `scripts/aar_pro_readiness.py` compiles runtime modules, rejects source-level truncation/synthetic chronology regressions, verifies the precision-distance formula numerically, and checks DRO-ARA observer circuit-breaker output wiring.
- `prescribe_recovery()` provides a deterministic self-healing plan from each witness, `docs/operations/aar_pro_v1_invariants.yaml` stores the machine-readable invariant registry, and `formal/AAR_PRO_V1.tla` records chronology and fail-closed invariants as a formal contract.
- Commit-acceptor validation is scoped with `--acceptor-id canonical-action-result-comparator --acceptor-id aar-pro-verification-suite --acceptor-id aar-pro-operational-governance` so AAR-PRO evidence validation is warning-clean, per-claim file-count caps stay enforced, and unrelated historical acceptor evidence gaps do not mask this claim.
- Falsification now rejects synthetic `3*step_index` chronology, minimum-length contract false breakers, unbounded ARA buffers, and requires DRO-ARA to expose belief mean, positive belief variance, dynamic free-energy threshold, recovery action, and causal chronology hash.
- Precision-extreme tests fuzz ultra-small positive variances and large deltas to prove rollback is finite and deterministic, while zero variance remains invalid input.
- `ControlEpisode.receive_afferentation()` annuls out-of-order afferentation into an invalid rollback witness while preserving a monotonic hash chain and closing the episode.
- `DRO-ARA` allocates comparator chronology through a monotone SHA-256 event chain, computes a Gaussian variational-energy surrogate from comparator error and belief variance, bounds error/energy buffers to `STABLE_RUNS`, exposes dynamic context-conditioned thresholds, and only trips `INVALID`/`REDUCE` when the adaptive threshold is breached.

## Evidence command

```bash
pytest -q -W ignore::DeprecationWarning nak_controller/tests/test_aar.py tests/unit/control/test_action_result_comparator.py tests/unit/control/test_control_episode.py tests/unit/control/test_precision_extremes.py tests/unit/control/test_self_healing.py tests/integration/control/test_action_result_comparator_integration.py tests/integration/control/test_aar_pro_smoke_script.py tests/integration/control/test_aar_pro_readiness_script.py tests/formal/test_aar_pro_tla_spec.py tests/formal/test_aar_pro_invariants_yaml.py tests/core/dro_ara/test_invariants.py tests/core/dro_ara/test_falsification.py
```

## Falsifier command

```bash
python -m pytest -q -W ignore::DeprecationWarning tests/unit/control/test_action_result_comparator.py::test_14b_precision_inversion_is_falsifiable tests/unit/control/test_precision_extremes.py tests/unit/control/test_action_result_comparator.py::test_01d_action_result_evidence_is_deterministic_and_tamper_evident tests/unit/control/test_action_result_comparator.py::test_01e_action_result_evidence_rejects_stale_or_forged_witness tests/unit/control/test_self_healing.py tests/integration/control/test_aar_pro_smoke_script.py tests/integration/control/test_aar_pro_readiness_script.py tests/formal/test_aar_pro_tla_spec.py tests/formal/test_aar_pro_invariants_yaml.py tests/core/dro_ara/test_falsification.py::test_dro_ara_exposes_dynamic_belief_and_causal_chronology tests/core/dro_ara/test_falsification.py::test_dro_ara_no_synthetic_step_index_chronology
```

## Evidence artifact

- `artifacts/aar_pro/action_result_comparator_pytest.txt`
