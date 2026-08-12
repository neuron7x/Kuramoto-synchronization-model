# Closure Ledger

Tracks issues touched by closure claims that warrant scrutiny under the closure
law (`issue closed only by source-level mechanism + tests + CI + ledger`).
Scanner: `tools/governance/check_fake_closure_claims.py` (advisory).

| issue | pr | closure_claim | actual_status | unchecked_non_waivable | scanner_state | recommended_action | final_resolution |
|-------|-----|---------------|---------------|------------------------|---------------|--------------------|------------------|
| #1109 | #1140 | `Closes #1109` | OPEN (reopened) | `energy_like_drift`, `phase_spread_bound`, `solver_metadata`, `stiffness_assumption`, `cross_solver_reference` | ADVISORY_FAIL | Downgrade to `Refs #1109`; build source-level `SecondOrderStabilityAudit` | #1140 body corrected to `Refs #1109`; #1109 reopened; source object still owed |
| #1096 | #1143 | `Closes #1096` | OPEN | none expressed as checkboxes (lanes are prose) | PASS (false negative) | Downgrade to `Refs #1096` (FP-1 = Lane A only of 5 lanes) | Flagged on PR #1143 for human review; scanner blind to prose-lane overreach |
| #1101 | #1140 | `Closes #1101` | CLOSED | none | UNKNOWN (closed, no checklist) | none — source landed in #1098/#1102/#1106 | Closure defensible; left closed |
| #1107 | #1140 | `Closes #1107` | CLOSED | none verifiable | UNKNOWN (closed, no checklist) | none — source landed earlier | Closure defensible; left closed |

## Notes

- **#1109 is the canonical fake-closure regression** and is encoded as the test
  fixture `tests/fixtures/fake_closure/issue_1109_non_waivable.md`.
- **#1096 is the canonical false-negative**: a real overclaim the checkbox
  heuristic cannot see. Documented as a scope limit, not a scanner pass.
- Live scanner verdicts here are point-in-time; re-run `--pr N` to refresh.
