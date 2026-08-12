# Critical-30 Ledger — evidence-derived, ranked, classified (2026-07-21)

Every row is drawn from an **authoritative registry**, not invented:
`governance/remediation_ledger.v1.json` (OPEN items), `docs/audit/FRACTAL_HEALTH_MAP_2026-07-21.md`,
the deterministic teeth instrument (`scripts/ci/audit_invariant_teeth.py`: BOUND_GREEN=49 /
GAP_UNBOUND=78 / GAP_SOURCE=4 / GAP_SKIPONLY=1), `docs/requirements/traceability_matrix.md`,
and `docs/audit/false_confidence.md`.

**Classification** (first-principles honesty — an owner-decision is not fakeable as an engineering merge):
- `DONE` — already closed by the 11-MR consolidation; row records the proof, no new work.
- `ENG` — engineering-closeable now with a falsifiable teeth test + merge.
- `OWNER` — requires Yaroslav's governance decision; deliverable is a *decision-ready artifact*, never a forced conversion.
- `MULTI` — genuinely multi-session (independent replication, threat model); deliverable is the *scaffold + first increment*, honestly scoped.

Done-criterion column is **falsifiable**: the exact gate/test whose GREEN proves closure.

| # | ID | Task | Source | Class | Falsifiable done-criterion |
|---|----|------|--------|-------|----------------------------|
| 1 | GATES-CI | Whole-tree meta-ratchet runs on a **live platform** (GitLab CI), not just pre-push | health-map "gates exist but do not run"; false-conf C5; GOV-008 | ENG | `.gitlab-ci.yml` has a job invoking `run_all_gates.py`, `allow_failure:false` |
| 2 | RTM-GATE | Gate that verifies each RTM requirement's mapped **Tests import its mapped Core modules** | RTM unverified (no gate greps `traceability_matrix`) | ENG | `check_rtm_traceability.py` FIRES on a fake link, GREEN on real |
| 3 | NFR-001 | Re-link Observability RTM row to tests that actually import `core/telemetry.py` | RTM: 3 mapped tests have 0 `core.telemetry` refs | ENG | RTM-GATE GREEN for NFR-001 |
| 4 | NFR-002 | Re-link Performance RTM row to tests that import `core/accelerators`,`execution/hft` | RTM: 3 mapped perf tests have 0 accel/hft refs | ENG | RTM-GATE GREEN for NFR-002 |
| 5 | FALSIFIER-CI | Claim `falsifier.test_id` node-resolution enforced on live CI | MR!37 | DONE | `claim-falsifier-nodes` job green (main 5386814d) |
| 6 | TEETH-SRC | GAP_SOURCE=4 — invariant witnesses whose declared source file does not exist | teeth instrument | ENG | `audit_invariant_teeth.py` GAP_SOURCE→0 |
| 7 | TEETH-SKIP | GAP_SKIPONLY=1 — witness collects but every node skipped | teeth instrument | ENG | GAP_SKIPONLY→0 (real assertion runs) |
| 8 | FALSE-CONF-CI | Wire `false_confidence_detector` into CI (advisory) — C5 self-referential fix | false-conf C5 "validators ship UNWIRED" | ENG | job runs detector, uploads report |
| 9 | ARC-016 | Prove OMS idempotency + conservation (formal witness) | MR!35 fixed TOCTOU; ledger ARC-016 OPEN | DONE→verify | OMS concurrent-idempotency teeth test green |
| 10 | OPS-003 | Validate rollback/kill-switch/recovery fault-injection | ledger OPS-003; MR!34 | ENG | fault-injection test drives kill_switch corrupt-state→fail-closed |
| 11 | TST-015 | Fault-injection / negative-path suite (kill-switch, OMS, circuit-breaker) | ledger TST-015 | ENG | negative-path tests exist + green |
| 12 | ARC-009 | Runtime `print()` debt in 11 files → structured logger | ledger ARC-009 | ENG | debt-ratchet print-count decreases; 0 in capital surfaces |
| 13 | ARC-007 | Broad-except in capital surfaces → typed/fail-closed | ledger ARC-007 (129 files) | ENG | `check_silent_procedures` capital-surface subset GREEN, count↓ |
| 14 | ARC-011 | Remove first-party `src.*` imports (19) | ledger ARC-011; ADR-0024 executed | DONE→verify | `grep -r 'from src\.' ` = 0 in tracked py |
| 15 | ARC-012 | Reduce `sys.path`/path-hacks (55) | ledger ARC-012; import-arch ratchet | ENG | import-architecture ratchet count↓, no new inserts |
| 16 | TST-007 | Classify 211 skip/xfail markers in 113 files | ledger TST-007; skip-ratchet exists | ENG | classification doc + skip-ratchet baseline frozen |
| 17 | REL-013 | Forbid stale generated artifacts | ledger REL-013; health-map G5 | ENG | `check_artifact_freshness` in CI, GREEN |
| 18 | TEETH-U1 | Bind witness: `oms` invariants (capital-critical, currently unbound) | GAP_UNBOUND | ENG | audit binds `oms` → BOUND_GREEN |
| 19 | TEETH-U2 | Bind witness: `dopamine` RPE invariant | GAP_UNBOUND | ENG | `dopamine` bound |
| 20 | TEETH-U3 | Bind witness: `kelly` sizing invariant (capital) | GAP_UNBOUND | ENG | `kelly` bound |
| 21 | TEETH-U4 | Bind witness: `capital_weighted_kuramoto` | GAP_UNBOUND | ENG | bound |
| 22 | TEETH-U5 | Bind witness: `adaptive_criticality` | GAP_UNBOUND | ENG | bound |
| 23 | DOP-PROMO | Dopamine claim-promotion: soften-to-P2 vs complete-evidence | health-map G5/gov; ledger | OWNER | decision-ready artifact w/ both option chains costed |
| 24 | DATA-LIC | Dataset licensing (askar-*/binance-* UNKNOWN) | health-map G4; SEC-015 | OWNER | licensing decision matrix, per-dataset |
| 25 | TST-004 | Reconcile 98% aspirational vs 90% release coverage floor | ledger TST-004 | OWNER | reconciliation doc, single SSOT threshold proposed |
| 26 | REL-014 | Formal release verdict | ledger REL-014; REL-011 RED-by-design | OWNER | verdict artifact honestly reports NOT_READY + gap list |
| 27 | RES-014 | Negative-evidence / tombstone preservation gate | ledger RES-014; `check_tombstone` exists | ENG | tombstone gate in CI, GREEN |
| 28 | GOV-008 | Traceability task→commit→test→artifact→gate skeleton | ledger GOV-008 | ENG | this ledger + RTM-GATE + GATES-CI = first spine link |
| 29 | RES-004 | Dimensional/units audit for the 7 physics laws | ledger RES-004 | MULTI | audit scaffold + T1 units checked as first increment |
| 30 | SEC-009 | Repository threat model | ledger SEC-009 | MULTI | threat-model scaffold (STRIDE headers) + attack-surface enum |

## Execution policy
- `ENG` rows: real fix + teeth test + merge, one MR per coherent group. No fake-green.
- `OWNER` rows: a decision artifact that costs each option; **generating fake PASS evidence to
  clear an owner-decision is forbidden** (health-map dopamine precedent).
- `MULTI` rows: honest scaffold + first increment; the ledger says what is NOT yet done.
- Every `check_*` gate touched must FIRE on an injected violation (mandatory-destruction discipline)
  before its MR merges.

## Honesty ledger (what "solve 30" does NOT mean)
Rows 23–26 are owner-decisions and 29–30 multi-session: these are *advanced to decision/scaffold
state*, not falsely marked closed. Rows 5, 9, 14 were already closed by prior MRs; recorded here
for the spine, not re-done. The genuinely new engineering closures this pass are rows 1–4, 6–8,
10–13, 15–22, 27–28.
