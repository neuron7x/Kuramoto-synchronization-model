# PR 1400 Verification Matrix

Status: draft gate matrix for `second-order-energy-stream-clean`.

## Change under review

`core/kuramoto/second_order.py` changes the audit energy evaluator from trajectory-wide dense pairwise allocation to one-snapshot pairwise evaluation.

## Invariant ledger

| Invariant | Required outcome | Evidence source |
|---|---:|---|
| Swing-energy formula unchanged | must hold | code review + physics tests |
| Peak pairwise memory reduced | `O(N^2)` | code review + metadata |
| No stability overclaim | must hold | docs + metadata |
| Partial audit remains partial | must hold | `remaining_gaps`, `promotion_allowed` |
| Mutation floor not lowered | must hold | mutation ratchet |
| Python quality intact | must hold | PR Gate / Code Hygiene |
| Import architecture intact | must hold | Import Architecture Gate |
| Physics behavior intact | must hold | Physics Invariants / Kernel / Reliability |

## Audited file scope

Actual PR scope contains ten files:

- `.claude/commit_acceptors/second-order-energy-stream-clean.yaml`
- `.github/workflows/mutation-kill-gate.yml`
- `core/kuramoto/second_order.py`
- `docs/ENGINEERING_RESEARCH_QUALITY_CODE.md`
- `docs/PR_1400_VERIFICATION_MATRIX.md`
- `pyproject.toml`
- `scripts/ci/check_mutation_kill_ratchet.py`
- `tests/ci/test_mutation_kill_ratchet.py`
- `tests/unit/physics/test_second_order_stability_audit.py`
- `tools/mutation_probe.py`

## Gate policy

Draft remains draft until all required gates are green:

- Mutation Kill Gate
- Commit Acceptor Gate
- PR Gate / python-quality
- Physics Invariants
- Physics Kernel Gate
- Physics Reliability Gate
- Code Hygiene Gate
- Import Architecture Gate
- Readiness Gate

## Final verdict rule

- Any required red gate => `BLOCK`.
- Any missing required gate => `REVISE`.
- All required gates green and claim scope unchanged => `ACCEPT`.
- Growing entropy without added falsification => `CLOSE`.
