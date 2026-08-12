# Action-Result Acceptor Salvage

**Status:** First-pass salvage audit, no runtime changes.
**Branch:** `audit/action-result-acceptor`
**New repo HEAD at audit time:** `e66946c`
**Old repo audited:** `Kuramoto-synchronization-model-main (2)`
**Generated:** 2026-04-27

---

## Final law (operationalised, not aspirational)

> action without result acceptance is just execution;
> result without error signal is just logging;
> error without update or rollback is just analytics.

This document and its sibling artefacts encode that law as a fail-closed
machine check. Every `OPERATIONAL` ledger entry must declare the full
chain:

```
action_source → expected_result → observed_result → error_signal
              → update_rule | rollback_rule
              → memory_effect → falsifier → existing_tests
```

Companions:

- `.claude/archive/ACTION_RESULT_ACCEPTOR_LEDGER.yaml` — 18 entries.
- `tools/archive/validate_action_result_acceptor.py` — fail-closed
  validator + deterministic JSON summary.
- `tests/archive/test_action_result_acceptor_ledger.py` — 21 tests
  pinning every rule plus a falsifier round-trip.
- `artifacts/archive/old_action_result_acceptor_hits.txt` — 1902 hits.
- `artifacts/archive/new_action_result_acceptor_hits.txt` — 2213 hits.

---

## Headline finding

The canonical Acceptor-of-Action-Result is **already implemented** in the
new repo:

```
nak_controller/aar/
├── types.py    — ActionEvent, Prediction, Outcome, ErrorSignal, AAREntry
├── core.py     — compute_error(prediction, outcome) → ErrorSignal
└── memory.py   — AARTracker.record_action / record_outcome / aggregators
```

This means the protocol's PR-2 step ("add canonical
`ActionResultAcceptor` contract") simplifies to **verify-and-link**:
expose this lineage at `geosync_hpc/control/` only as a thin adapter
over the existing AAR primitives. No fresh data classes needed.

---

## Distribution of the 18 ledger entries

| Status            | Count | Notes                                                                |
|-------------------|------:|----------------------------------------------------------------------|
| `OPERATIONAL`     |    13 | Full action→error→update/rollback chain with tests + falsifier.     |
| `PARTIAL`         |     2 | Mechanism real but loop incomplete (prompt-outcome, strategy-record). |
| `PRESENT_IN_NEW`  |     1 | PromptExecutionRecord (logging artefact, not an acceptor).          |
| `DECORATIVE`      |     1 | orchestrator naming-only.                                            |
| `UNKNOWN`         |     1 | benchmarks/neuro_optimization_bench.py — pre-audit.                  |

| Migration action  | Count |
|-------------------|------:|
| `KEEP_NEW`        |    14 |
| `REWRITE`         |     2 |
| `INVESTIGATE`     |     1 |
| `(other)`         |     1 |

| Importance        | Count |
|-------------------|------:|
| `CRITICAL`        |     3 |
| `HIGH`            |     9 |
| `MEDIUM`          |     5 |
| `LOW`             |     1 |

---

## Mechanism inventory

### `EXECUTION_RESULT_ACCEPTOR`
1. `nak_controller/aar/types.py` — ActionEvent / Prediction / Outcome / ErrorSignal / AAREntry.
2. `nak_controller/aar/core.py` + `memory.py` — AARTracker loop with EMA per agent / mode.
3. `analytics/regime/src/core/geosync_v21.py` — ProbabilityBacktester / RegimeHMMAdapter / block-bootstrap.
4. `cli/geosync_cli.py` — sha256 artefact hash + Watchdog + parity gate on every subcommand.

### `CONSENSUS_FEEDBACK_ACCEPTOR`
5. `analytics/regime/src/consensus/hncm_adapter.py::HNCMConsensusAdapter.update_feedback` — realized → RPE → EMA weights.
6. `analytics/regime/src/consensus/hncm_neuro.py::NeuroConsensusAdapter` — eligibility trace + metaplasticity gain + Page–Hinkley α adapt.
7. `learned_weights()` clamp [0.05, 1.0].

### `STRATEGY_MEMORY_ACCEPTOR`
8. `core/agent/memory.py::StrategyRecord` — partial: stores past performance but does not update on subsequent realized outcomes.
9. `core/agent/memory.py::StrategyMemory._decayed_score` — operational decay.
10. `core/agent/evaluator.py::EvaluationResult` — succeeded / error invariant.

### `PROMPT_OUTCOME_ACCEPTOR`
11. `core/agent/prompting/models.py::PromptOutcome` — partial: caller-supplied success boolean.
12. `core/agent/prompting/models.py::PromptExecutionRecord` — logging artefact only (non-claim).
13. `core/agent/prompting/library.py::_PromptSuite.rollback_to_control` — rollback path is well-formed but unprotected by tests.

### `RISK_GUARDIAN_ACCEPTOR`
14. `apps/risk_guardian/engine.py::RiskGuardian` — kill-switch on max-drawdown breach.
15. `apps/risk_guardian/engine.py` — safe-mode sizing brake (distinct from full halt).

### `CLAIM_RESULT_ACCEPTOR`
16. `.claude/claims/validate_claims.py` — claims → falsifier → tests gate (the repository's own meta-acceptor).

### `DECORATIVE_LABEL`
17. `core/agent/orchestrator.py` — wiring layer; explicit non-claim.

### `UNKNOWN`
18. `benchmarks/neuro_optimization_bench.py` — `INVESTIGATE` until classified.

---

## Recommended PR sequence

| PR     | Scope                                                                 |
|--------|------------------------------------------------------------------------|
| PR-A1  | Adapter `geosync_hpc/control/action_result_acceptor.py` over the existing `nak_controller/aar/` primitives (canonical contract, no new data classes). |
| PR-A2  | `tests/unit/control/test_action_result_acceptor.py` covering the protocol's 12 required cases (result match / mismatch / update / rollback / insufficient observation / dimension mismatch / NaN / negative threshold / determinism / frozen witness / forbidden imports). |
| PR-A3  | Bridge legacy outcome mechanisms (PromptOutcome, HNCM update_feedback, StrategyRecord, RiskGuardian) to the canonical witness. Adapter only; one test + one falsifier per bridge. |
| PR-A4  | Port-tests-before-code: lift the rollback-path tests for `_PromptSuite.rollback_to_control` and the StrategyMemory feedback loop into `tests/unit/control/test_legacy_action_result_acceptor_behavior.py`. Mark current failures `xfail` only with explicit migration-target IDs in the ledger. |

---

## Local commands

```bash
python tools/archive/validate_action_result_acceptor.py
python -m pytest tests/archive/test_action_result_acceptor_ledger.py -v
python -m ruff check tools/archive/validate_action_result_acceptor.py tests/archive/test_action_result_acceptor_ledger.py
python -m ruff format --check tools/archive/validate_action_result_acceptor.py tests/archive/test_action_result_acceptor_ledger.py
python -m black --check tools/archive/validate_action_result_acceptor.py tests/archive/test_action_result_acceptor_ledger.py
python -m mypy --strict tools/archive/validate_action_result_acceptor.py tests/archive/test_action_result_acceptor_ledger.py
```

The validator emits `tmp/action_result_acceptor_validation.json` on every
run with deterministic field ordering and counts (entry_count,
critical_count, high_count, missing_in_new_count, port_count,
rewrite_count, archive_count, reject_count).
