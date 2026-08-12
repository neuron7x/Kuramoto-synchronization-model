# D-002G-P3 — Implementation Report

> **Claim boundary (verbatim).**
>
> This PR implements D-002G-P3 constant-payload null-admissibility adjudication infrastructure only. It does NOT establish D-002G scientific PASS. It does NOT authorise canonical D-002G run. It does NOT update D002C_CLAIM_LEDGER.yaml. B1 may only be updated according to explicit eligibility evidence in this PR. B2 remains a separate blocker, unchanged.

## 1. Anchor

* Branch: `feat/x10r-d002g-p3-constant-payload-null-recovery`.
* Base sha (worktree branched off): `2b3872c` (P2 head, PR #679
  pre-merge). Protocol §3 references the post-#679-merge sha
  `7b386ef3...` as the rebase target on main; this PR is fully
  rebase-compatible with that post-merge state by construction
  (no edit to locked files, no edit to P2 surface modules outside
  the additive extension to `d002g_null_mechanisms.py`).
* HEAD sha: recorded at commit time.

## 2. Locked-files invariant — PASS

The pre-existing P2 locked-files test
(`tests/systemic_risk/test_d002g_m2_locked_governance_untouched.py`)
pins ten files at the P1 merge anchor `d3400c2e`. P3 does NOT
modify any of those files; the test continues to PASS on this
branch.

P3 additionally pins the on-disk sha of `D002C_CLAIM_LEDGER.yaml`
in `tests/systemic_risk/test_d002g_p3_no_canonical_promotion.py::
test_p3_no_d002c_ledger_touch` — fail-closed on any byte drift.

## 3. Module list

| Module / file | LoC delta | Role |
|---|---|---|
| `research/systemic_risk/d002g_null_mechanisms.py` | +~620 (extend) | M2 node-payload + injection-sequence sub-domain verifiers + realisers, 10 new verdict literals, salt constants, dispatch routing. |
| `tests/systemic_risk/test_d002g_p3_node_payload_null.py` | +~280 (new) | 11 node-payload tests (8 required + 3 dispatch). |
| `tests/systemic_risk/test_d002g_p3_injection_sequence_null.py` | +~280 (new) | 11 injection-sequence tests (8 required + 3 dispatch). |
| `tests/systemic_risk/test_d002g_p3_constant_payload_blockers.py` | +~110 (new) | 4 B1/B2 invariant tests. |
| `tests/systemic_risk/test_d002g_p3_no_canonical_promotion.py` | +~165 (new) | 6 claim-boundary / ledger-pin tests. |
| `tests/systemic_risk/test_d002g_p3_traps.py` | +~210 (new) | 8 adversarial trap tests. |
| `docs/governance/D002G_P3_DISCOVERY_REPORT.md` | new | Phase 0 discovery output. |
| `docs/governance/D002G_P3_NULL_DOMAIN_CONTRACTS.md` | new | Phase 1 admissibility contracts. |
| `docs/governance/D002G_P3_ELIGIBILITY_MATRIX.md` | new | Phase 5 long-form matrix. |
| `docs/governance/D002G_P3_M3_PREREGISTRATION.md` | new | M3 pre-registration draft (locked at merge commit). |
| `docs/governance/D002G_P3_IMPLEMENTATION_REPORT.md` | this file | Phase 11 implementation report. |
| `docs/governance/D002G_CANONICAL_RUN_BLOCKERS.md` | +~25 (extend) | §B1.P3 subsection appended. |
| `artifacts/d002g/p3/null_domain_verdicts.json` | new | Machine-readable verdict matrix. |
| `.claude/commit_acceptors/x10r-d002g-p3-constant-payload-null-recovery.yaml` | new | Diff-bound commit acceptor for this PR. |

No file outside this list is touched. All P1 + P2 locked files
remain byte-exact unchanged.

## 4. New public API symbols

Module: `research.systemic_risk.d002g_null_mechanisms`

```python
# salts
M2_NODE_PAYLOAD_SALT: Final[int] = 313
M2_INJECTION_SEQUENCE_SALT: Final[int] = 419

# verifiers
def verify_m2_node_payload_eligibility(...) -> M2EligibilityVerdict: ...
def verify_m2_injection_sequence_eligibility(...) -> M2EligibilityVerdict: ...

# realisers
def realize_m2_node_payload_null(...) -> tuple[NDArray[np.float64], dict[str, Any]]: ...
def realize_m2_injection_sequence_null(...) -> tuple[NDArray[np.float64], dict[str, Any]]: ...

# dispatch extended
def realize_null(..., shuffle_domain: Literal["edge_weight", "node_payload", "injection_sequence"] = "edge_weight") -> NullRealization: ...
```

10 new verdict literals added to `M2EligibilityStatus`:

```
ELIGIBLE_M2_NODE_PAYLOAD
INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL
INELIGIBLE_M2_NODE_PAYLOAD_MISSING_DOMAIN
INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED
INDETERMINATE_M2_NODE_PAYLOAD_PROVENANCE_MISSING
ELIGIBLE_M2_INJECTION_SEQUENCE
INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE
INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION
INELIGIBLE_M2_INJECTION_SEQUENCE_MISSING_DOMAIN
INDETERMINATE_M2_INJECTION_SEQUENCE_PROVENANCE_MISSING
```

Existing edge_weight verdicts are preserved unchanged. P1 + P2
tests remain green (66 / 66 in the consolidated suite).

## 5. Eligibility matrix (paste from Phase 5)

| Substrate | N | M1 | M2_EDGE_WEIGHT | M2_NODE_PAYLOAD | M2_INJECTION_SEQUENCE | FINAL_NULL_DOMAIN | B1 contribution |
|---|---:|---|---|---|---|---|---|
| `ricci_flow` | 50 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M1 | ELIGIBLE |
| `ricci_flow` | 100 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M1 | ELIGIBLE |
| `ricci_flow` | 200 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M1 | ELIGIBLE |
| `block_structured` | 50 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `block_structured` | 100 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `block_structured` | 200 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `temporal_coupling` | 50 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `temporal_coupling` | 100 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `temporal_coupling` | 200 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | M3_REQUIRED | INELIGIBLE_M2_FULL |

## 6. B1 closure rule (§11 — verbatim)

> B1 may only move from `OPEN_PARTIAL` → `CLOSED_FOR_ELIGIBILITY_ONLY` if and only if:
>
>   1. all prereg-scoped substrates (ricci_flow, block_structured, temporal_coupling) have at least one ELIGIBLE null strategy;
>   2. each admissible strategy has deterministic same-seed replay;
>   3. each admissible strategy preserves required topology semantics (topology_hash invariant);
>   4. each strategy has non-degenerate null contrast (assignment changes when admissible);
>   5. all fail-closed adversarial traps pass;
>   6. no claim boundary violation;
>   7. D002C ledger byte-exact unchanged;
>   8. B2 is still represented as a SEPARATE open blocker.
>
> Even if B1 closes:
>   canonical_run_authorized = false
> unless B1 == CLOSED_FOR_ELIGIBILITY_ONLY AND B2 == CLOSED_OR_SCOPED_ACCEPTED AND no future blocker exists AND an explicit canonical-run authorization artifact exists. NONE of those conditions can be created by this PR.

Applied to P3:

| Rule | This PR |
|---|---|
| 1 — all 3 substrates have ELIGIBLE | NO — `block_structured` & `temporal_coupling` have NONE across M1/M2 |
| 2 — same-seed replay | yes (verified by tests) |
| 3 — topology-hash invariant | yes (verified by tests) |
| 4 — non-degenerate null contrast | yes (verified by tests; INELIGIBLE verdicts honestly recorded) |
| 5 — adversarial traps PASS | yes (8/8 traps green) |
| 6 — no claim-boundary violation | yes (verified by claim-boundary tests) |
| 7 — D002C ledger byte-exact | yes (sha256 pin test green) |
| 8 — B2 still separate | yes (B2 untouched) |

→ Rule 1 fails. **B1 stays OPEN_PARTIAL, upgraded to OPEN_REQUIRES_M3.**

## 7. P3 decision state

**`P3_M3_PREREGISTRATION_REQUIRED`**

Per the protocol's allowed terminal states, this is the honest
scientific outcome: the M1 ∪ M2 admissibility surface is
exhausted on two of three prereg substrates. M3 pre-registration
shipped at `docs/governance/D002G_P3_M3_PREREGISTRATION.md`,
locked at this PR's merge commit.

## 8. Test summary

| Test file | Test count | Status |
|---|---:|---|
| `test_d002g_p3_node_payload_null.py` | 11 | PASS |
| `test_d002g_p3_injection_sequence_null.py` | 11 | PASS |
| `test_d002g_p3_constant_payload_blockers.py` | 4 | PASS |
| `test_d002g_p3_no_canonical_promotion.py` | 6 (4 active + 2 conditional) | PASS |
| `test_d002g_p3_traps.py` | 8 | PASS |
| **Total P3** | **40** | **PASS** |

P1 + P2 consolidated test surface still PASSES unchanged (66
tests with `-k "d002g or d002c or m2"`).

## 9. Quality gates (scoped to changed files)

```
ruff format --check <P3 changed files>            PASS
ruff check <P3 changed files>                     PASS
black --check <P3 changed files>                  PASS
mypy --strict --follow-imports=silent <P3 .py>    PASS
pytest tests/systemic_risk/ -k "d002g or d002c or p3 or m2 or m3" -q   PASS
```

Repo-wide ruff/black/mypy is dirty from main (pre-existing P1+P2
state); per the protocol's `PHASE 9` scope rule the P3 PR does
NOT clean it.

## 10. Out-of-scope (explicit)

* No canonical D-002G sweep was executed.
* No `D002C_CLAIM_LEDGER.yaml` mutation. sha256 pinned & verified.
* No D-002G tier promotion. No `SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN` claim.
* No cross-promotion to D-002C. The D-002C ledger remains
  append-only at its attempt-2 falsification.
* No M1 / M6 / M2-edge-weight code path edits. All three remain
  byte-exact unchanged at the line level (verified via P2 test).
* No B2 closure claim.
* No M3 implementation. M3 pre-registration only (locked at merge).

## 11. Closure status

| Blocker | Status pre-P3 | Status post-P3 |
|---|---|---|
| B1 (substrate eligibility) | OPEN_PARTIAL | **OPEN_REQUIRES_M3** |
| B2 (percentile-CI limitation) | OPEN | OPEN (untouched) |
| canonical_run_authorized | false | false (unchanged) |
| D002C_ledger | UNTOUCHED | UNTOUCHED (sha pin verified) |

## 12. Next recommended PR

**D-002G-M3 implementation** — per the M3 pre-registration draft
in `D002G_P3_M3_PREREGISTRATION.md §8 review checklist`.
Salt 523 reserved.
