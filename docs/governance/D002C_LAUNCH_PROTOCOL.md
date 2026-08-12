# D-002C Launch Protocol

**Class.** Operator runbook for the D-002C Signal Amplification Sweep.
**Scope.** Synthetic-only; INV-IDENTIFICATION-1 globally active.
**Status.** Launch-gating layer; emits no claim of its own.

---

## Purpose

Reduce the full launch path to a deterministic, auditable, fail-closed
sequence of commands. The operator's job is to provide the four
preflight capsules; the script does the rest.

## Non-goals

- This document does NOT promote a verdict into any tier beyond
  what the C2.1-locked pre-registration permits.
- This document does NOT relax R1/R2/R3 thresholds.
- This document does NOT replace the pre-registration YAML as the
  single source of truth.

## Pre-flight requirements

Before running the launch script, you MUST have four preflight
capsule files in `<preflight-dir>/`:

| File | Source module | Required verdict |
|---|---|---|
| `pos_control.json` | `research/systemic_risk/d002c_pos_control.py` | (excluded_combos populated; not a launch-gate) |
| `neg_control.json` | `research/systemic_risk/d002c_neg_control.py` | (excluded_cells populated; not a launch-gate) |
| `null_audit.json` | `research/systemic_risk/d002c_null_audit.py` | every audited cell PASS |
| `smoke_test.json` | `research/systemic_risk/d002c_smoke_test.py` | verdict = PASS |

Each capsule carries a content-addressed `sha256`. The runner refuses
to launch if any capsule is missing, malformed, or sha-mismatched.

## Launch command

```bash
python -m scripts.run_x10r_d002c_signal_amplification_sweep \
    --preregistration docs/governance/D002C_PREREGISTRATION.yaml \
    --preflight-dir tmp/d002c_preflight \
    --checkpoint tmp/d002c_sweep_checkpoint.json \
    --output-dir tmp/d002c_sweep_output
```

Exit codes:

- `0` — tier = `SYNTHETIC_GATE6_CERTIFIED_REDESIGN_N_LE_200`
- `1` — tier = `D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET`
- `2` — infrastructure refusal (corrupt prereg / capsule / config mismatch)

Add `--null-audit-failed` if the null-audit capsule reports a FAIL
on any audited cell (forces tier=FAIL regardless of R1/R2/R3).

## Resume protocol

The script is idempotent under the D-002D atomic checkpoint:

```bash
# Kill mid-flight (Ctrl-C or process crash) — checkpoint survives.
# Re-launch with the same arguments — sweep resumes from the last
# completed cell.
python -m scripts.run_x10r_d002c_signal_amplification_sweep \
    --preregistration docs/governance/D002C_PREREGISTRATION.yaml \
    --preflight-dir tmp/d002c_preflight \
    --checkpoint tmp/d002c_sweep_checkpoint.json \
    --output-dir tmp/d002c_sweep_output
```

**Capsule rotation discipline (Codex P1 contract):** if the preflight
capsules CHANGE between launch and resume, the runner refuses with
`PreflightLaunchRefused: checkpoint contradicts current preflight
decision`. Three drift modes are caught: persisted-skipped-now-runnable,
persisted-computed-now-excluded, and source-capsule-sha-drift. Fix by
starting a fresh checkpoint path or by reverting capsules.

## Expected wallclock

- ~16 hours on 6 worker processes (canonical envelope)
- Checkpoint written every cell — zero recovery cost on crash

## Verdict semantics

The verdict deriver (`research/systemic_risk/d002c_verdict.py`) applies
three rules from the pre-registration:

| Rule | Threshold | Source |
|---|---|---|
| R1 | `\|signal_mean\| / (CI_half_width) > 1.0` | locked YAML |
| R2 | `FPR(λ=0) <= 0.05` across matching null cells | locked YAML |
| R3 | direction stability >= 0.80 | locked YAML |

ALL three must pass at SOME (N, substrate, metric, λ>0) cell for
`tier = SYNTHETIC_GATE6_CERTIFIED_REDESIGN_N_LE_200`.

## Anti-overclaim guards

The verdict carries flags that scope the claim:

- **MARGINAL_PASS** — every passing rule is within 5% of its threshold.
  Independent re-sweep with a re-randomised substrate seed is required
  before promoting to certification.
- **SINGLE_PATH_PASS** — only one (substrate, metric) combination
  passes. The claim is scoped to that combination ONLY; no
  generalisation beyond.
- **NULL_AUDIT_FAIL** — verdict refused regardless of R1/R2/R3 (via
  `--null-audit-failed` CLI flag).

## Required tests

- `tests/research/systemic_risk/test_d002c_verdict.py` — 15 tests
  pinning the rule evaluators, anti-overclaim guards, sha determinism,
  input validation, and non-finite robustness.

## CI requirements

- `ruff check` clean on:
  - `research/systemic_risk/d002c_verdict.py`
  - `scripts/run_x10r_d002c_signal_amplification_sweep.py`
  - `tests/research/systemic_risk/test_d002c_verdict.py`
- `black --check` clean on the same set.
- `mypy --strict --follow-imports=silent` clean on the same set.
- `pytest tests/research/systemic_risk/test_d002c_verdict.py` PASS.
- `pytest tests/audit/test_false_confidence_detector.py` PASS.

## Rollback command

```bash
git revert <commit-sha-of-this-PR>
rm -f research/systemic_risk/d002c_verdict.py \
      scripts/run_x10r_d002c_signal_amplification_sweep.py \
      tests/research/systemic_risk/test_d002c_verdict.py \
      docs/governance/D002C_LAUNCH_PROTOCOL.md \
      .claude/commit_acceptors/x10r-d002c-launch.yaml
```

## Known limitations

1. The actual sweep wallclock (~16h on 6 workers) is not exercised
   on CI; only the launch infrastructure + verdict logic are
   validated there. Operator must verify wallclock budget on the
   target machine before launching.
2. R3 direction stability is treated as a binary pass via the sweep
   runner's `direction` field (which encodes the C2.1-locked
   `direction_consistency_min_seeds / n_seeds >= 0.80` check by
   construction). If a future sweep runner changes how `direction`
   is computed, the R3 numeric form will need to track that change.
3. `--null-audit-failed` is an out-of-band operator flag; this
   PR does not auto-parse the null-audit capsule's per-cell
   verdicts. A follow-up may wire `run_null_audit_from_capsule`
   directly into the launch script.

## Claim boundary

This script is **claim-neutral**. It emits a TIER (PASS or FAIL) per
the locked acceptance rule, plus anti-overclaim guards. It does NOT
promote any verdict into a real-data tier, a bank-level inference,
or a "production-ready" label. The forbidden output set in the
pre-registration YAML (`SYNTHETIC_GATE6_CERTIFIED`,
`VALIDATED_REAL_BANK_LEVEL_RESULT`, etc.) remains forbidden.

If the verdict is `SYNTHETIC_GATE6_CERTIFIED_REDESIGN_N_LE_200`, the
operator MUST follow the pre-registration's anti-overclaim guardrails
(§7 of the YAML) before any external communication.
