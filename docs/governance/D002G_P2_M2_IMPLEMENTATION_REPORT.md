# D-002G P2/M2 — Implementation Report (topology-preserving shuffle null)

## 1. Anchor

* Anchor commit (read-only): `d3400c2e981d947449c7457fd163c71e7abc0dab`
  (PR #677 P1 squash on `origin/main`).
* Branch: `feat/x10r-d002g-p2-m2-topology-preserving-shuffle`.
* HEAD sha: filled in at commit time.
* Pre-registration design anchor:
  `docs/governance/D002G_M2_TOPOLOGY_PRESERVING_NULL.md`.

## 2. Locked-files sha block (PASS)

All eight P1 anchor files plus the two P1 commit acceptors verified
byte-exact unchanged versus the anchor commit (`d3400c2e`):

| File | sha256 | Verdict |
|------|--------|---------|
| `docs/governance/D002G_PREREGISTRATION.yaml` | `1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04` | PASS |
| `docs/governance/D002G_NONDEGENERATE_NULL_DESIGN.md` | `9cef2db7f5d1f90eb9ec71524193c079efff024c35de0ea9758e4f6c747bd8bb` | PASS |
| `docs/governance/D002G_ACCEPTANCE_RULES.md` | `875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31` | PASS |
| `.claude/commit_acceptors/x10r-d002g-nondegenerate-null-redesign.yaml` | `eaa704722cd113997fac58d52de3ec38ac7197c70d80389e4197d52d8ce93327` | PASS |
| `docs/governance/D002C_PREREGISTRATION.yaml` | `b1561ddde08a60a8eed416f2103655e0f3ee1ecd4e2b2037f4e7193c424a154e` | PASS |
| `docs/governance/D002C_CLAIM_LEDGER.yaml` | `f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd` | PASS |
| `docs/governance/D002C_CANONICAL_RUN_REPORT.md` | `f03ed1c6e96f62dc7ff061b48fc44a6dce0679a13ca6bf449e3785f0a4833ed0` | PASS |
| `docs/governance/D002C_ATTEMPT_2_NULL_AUDIT_FALSIFICATION_REPORT.md` | `83164744e223f236a49111c6411630ff54332285ab871896bfc8921fcd4b0b34` | PASS |
| `.claude/commit_acceptors/x10r-d002g-p1-implementation.yaml` | `83d6f6bcfc276d9acb381c39c439ad669836a6a14ed123c3a78bd3920f526199` | PASS |
| `.claude/commit_acceptors/x10r-d002g-p1-strike-scaffolding.yaml` | `4a65261f8baf530ab307d138135b8771ffa20b81bd044781a14b91dd735e9608` | PASS |

These are pinned inside
`tests/systemic_risk/test_d002g_m2_locked_governance_untouched.py`;
the test fails closed on any drift.

## 3. Module list with LoC

| Module / file | LoC delta | Role |
|---|---|---|
| `research/systemic_risk/d002g_null_mechanisms.py` | +495 (extend) | M2 verifier, M2 realisation, `M2EligibilityVerdict`, `M2NotEligibleError`, `M2TopologyMutationError`, `_topology_hash`, `_build_precursor_delta`, `verify_m2_eligibility`, `_realize_m2`, dispatch from `realize_null`. |
| `tests/systemic_risk/test_d002g_m2_topology_preserving_shuffle.py` | +543 (new) | The 14 M2 contract tests (see §6). |
| `tests/systemic_risk/test_d002g_m2_locked_governance_untouched.py` | +59 (new) | Pin sha256 of the ten locked files at the P1 merge anchor. |
| `docs/governance/D002G_M2_TOPOLOGY_PRESERVING_NULL.md` | +332 (new) | M2 design + mechanism + verdict ladder + forbidden interpretations. |
| `docs/governance/D002G_P2_M2_IMPLEMENTATION_REPORT.md` | this file | P2/M2 implementation report. |
| `docs/governance/D002G_CANONICAL_RUN_BLOCKERS.md` | +50 (extend) | Append §B1.M2 with the partial-mitigation table. |
| `.claude/commit_acceptors/x10r-d002g-p2-m2-topology-preserving-shuffle.yaml` | new | Diff-bound commit acceptor for this PR. |

No file outside this list is touched. P1 tests and modules are
read-only — verified by the locked-files-untouched test.

## 4. Attack ladder

The M2 surface inherits the eight-rung adversarial discipline of
P1. The M2 specific attack surface is small; the table below
records each rung and its mitigation site.

| Rung | Attack | Mitigation | Test |
|---|---|---|---|
| M2-A1 | Topology drift under shuffle | `_topology_hash` post-check inside `_realize_m2`; verifier dry-run check | `test_m2_preserves_topology_hash`, `test_m2_rejects_topology_mutation` |
| M2-A2 | Node / edge count drift | Permutation operates on a fixed-cardinality support index set | `test_m2_preserves_node_and_edge_counts` |
| M2-A3 | Silent no-op on constant-valued payload (K_null == K_p bit-identically) | `distinct_values_count < 2` ⇒ `INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL` fail-closed | `test_m2_fails_closed_on_degenerate_shuffle_pool`, `test_m2_changes_payload_assignment_when_pool_non_degenerate` |
| M2-A4 | Hidden non-determinism (global RNG state) | `np.random.default_rng(int(null_seed))`; no global state; locked deterministic_mix seeding | `test_m2_is_deterministic_for_same_seed` |
| M2-A5 | RNG-stream collision M1 ↔ M2 ↔ M6 | Distinct salts: 10000 (M1 offset, additive) / 99 (M6) / 211 (M2); domain-separated via `deterministic_mix` | `test_m2_changes_for_different_seed_when_admissible` |
| M2-A6 | Empty support spuriously labelled ELIGIBLE | `support_mask.sum() < 1` ⇒ `INELIGIBLE_M2_INSUFFICIENT_TOPOLOGY` | `test_m2_fails_closed_on_insufficient_topology` |
| M2-A7 | Malformed precursor silently absorbed | `substrate.realize` exception ⇒ `INDETERMINATE_M2_PROVENANCE_MISSING` | `test_m2_rejects_missing_provenance` |
| M2-A8 | Locked governance mutation | `test_d002g_m2_locked_governance_untouched.py` pins ten file shas | `test_m2_does_not_modify_d002c_ledger` (D-002C ledger sub-pin); locked-files test (governance-wide pin) |

## 5. Eligibility verdicts (empirical, per substrate × N)

Sweep: `lambda_value=0.4`, `base_seed=42`, locked null-seed
formula `deterministic_mix(base_seed, M2_PLACEBO_SALT=211)`.

| Substrate | N | Status | support count | distinct values | shuffle_domain |
|---|---|---|---|---|---|
| `ricci_flow` | 50 | ELIGIBLE_M2 | 13 | 3 | edge_weight |
| `ricci_flow` | 100 | ELIGIBLE_M2 | 68 | 8 | edge_weight |
| `ricci_flow` | 200 | ELIGIBLE_M2 | 214 | 10 | edge_weight |
| `block_structured` | 50 | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | 775 | 1 | edge_weight |
| `block_structured` | 100 | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | 3100 | 1 | edge_weight |
| `block_structured` | 200 | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | 12400 | 1 | edge_weight |
| `temporal_coupling` | 50 | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | 1225 | 1 | edge_weight |
| `temporal_coupling` | 100 | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | 4950 | 1 | edge_weight |
| `temporal_coupling` | 200 | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | 19900 | 1 | edge_weight |

**Honest finding.** The stock `block_structured` substrate applies
a single constant inter-block lift `0.25·λ·K_c` to every off-
diagonal entry in its three precursor sub-blocks; the stock
`temporal_coupling` substrate applies a single constant additive
lift `0.15·λ·K_c` to every non-zero off-diagonal entry. The
resulting ΔK has exactly ONE distinct payload value per substrate
realisation. The M2 edge-weight shuffle is by construction a
permutation over the support payload multiset — when the multiset
is `{v, v, …, v}`, every permutation is a no-op. M2 in the
edge-weight sub-domain therefore CANNOT construct a non-degenerate
null on these two substrates, and the verifier emits
`INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL` fail-closed.

**Implication.** B1 is **PARTIALLY MITIGATED** — only the
`ricci_flow` cell becomes admissible under M2. The
`block_structured` and `temporal_coupling` cells remain
HARD-BLOCKED for the canonical D-002G run. See
`D002G_CANONICAL_RUN_BLOCKERS.md §B1.M2`.

Future-work hooks recorded in `M2EligibilityVerdict.
shuffle_domain ∈ {"node_payload", "edge_weight",
"injection_sequence"}` — alternate sub-domains are reserved and
NOT implemented here. A future PR may investigate whether
node-payload or injection-sequence shuffle sub-domains admit a
non-degenerate null on the two constant-payload substrates; this
PR ships the edge-weight contract only.

## 6. Tests

Two new test files, 14 + 1 tests total.

| File | Test name | Marker |
|---|---|---|
| `test_d002g_m2_topology_preserving_shuffle.py` | `test_m2_preserves_topology_hash` | fast |
| | `test_m2_preserves_node_and_edge_counts` | fast |
| | `test_m2_changes_payload_assignment_when_pool_non_degenerate` | fast |
| | `test_m2_is_deterministic_for_same_seed` | fast |
| | `test_m2_changes_for_different_seed_when_admissible` | fast |
| | `test_m2_fails_closed_on_insufficient_topology` | fast |
| | `test_m2_fails_closed_on_degenerate_shuffle_pool` | fast |
| | `test_m2_rejects_missing_provenance` | fast |
| | `test_m2_rejects_topology_mutation` | fast |
| | `test_m2_marks_block_structured_eligible_if_contract_satisfied` | fast |
| | `test_m2_marks_temporal_coupling_eligible_if_contract_satisfied` | fast |
| | `test_m2_does_not_modify_d002c_ledger` | fast |
| | `test_m2_claim_boundary_text_present` | fast |
| | `test_m2_no_scientific_pass_claim` | fast |
| `test_d002g_m2_locked_governance_untouched.py` | `test_locked_governance_files_unchanged_at_m2_anchor` | fast |

All 15 tests pass on the worktree commit. No xfail. No skip. P1
adversarial-strike tests (`test_d002g_strike_R1..R7_*`) unchanged
and still PASS (27 in the consolidated suite). The total
`d002g or d002c or m2` filter now runs 66 tests on this branch.

Single-seed determinism tests stay in the fast bucket — runtime
≈ 1.5 s. No `pytest.mark.slow` markers are required since the M2
test surface does not hit a multi-seed sweep.

## 7. Quality gates

All commands run from worktree root with `PYTHONPATH=.`.

```
$ ruff format --check research/systemic_risk/d002g_null_mechanisms.py \
                       tests/systemic_risk/test_d002g_m2_*.py
3 files already formatted

$ ruff check research/systemic_risk/d002g_null_mechanisms.py \
              tests/systemic_risk/test_d002g_m2_*.py
All checks passed!

$ black --check research/systemic_risk/d002g_null_mechanisms.py \
                tests/systemic_risk/test_d002g_m2_*.py
All done! ✨ 🍰 ✨

$ mypy --strict --follow-imports=silent \
        research/systemic_risk/d002g_null_mechanisms.py \
        tests/systemic_risk/test_d002g_m2_*.py
Success: no issues found in 3 source files

$ pytest tests/systemic_risk/ -k "d002g or d002c or m2" -q
66 passed in 1.8s
```

mypy `--follow-imports=silent` scopes the check to the changed
D-002G surface plus the new M2 tests; the pre-existing
`core/kuramoto/jax_engine.py` typing drift is unrelated to this
PR (same scope rule as P1).

## 8. CLAIM BOUNDARY (verbatim)

> This PR implements D-002G-P2/M2 null-admissibility infrastructure only. It does NOT establish D-002G scientific PASS. It does NOT authorise canonical D-002G run. Canonical run remains BLOCKED on the conjunction (B1 substrate eligibility — partially closed if M2 verdict is ELIGIBLE for the 2/3 substrate grid — AND B2 percentile-CI limitation AND any future blocker).

The 2/3 substrate grid is NOT achieved by this PR: M2 edge-weight
shuffle admits ONLY `ricci_flow`. B1 is therefore PARTIALLY
MITIGATED with empirical coverage 1/3 substrates ELIGIBLE under
the M1 ∪ M2 union (`ricci_flow` under either; `block_structured`
and `temporal_coupling` still INELIGIBLE under both). The
canonical D-002G run remains BLOCKED. The 2/3 wording above is
the PR-promise upper bound that would have been achieved if the
M2 edge-weight shuffle covered the constant-payload substrates;
it does not, so the empirical mitigation is 1/3, recorded honestly
in §5.

## 9. Out-of-scope (explicit)

* No canonical D-002G sweep was executed. No Phase 0 capsule was
  emitted on the prereg-scoped grid.
* No `D002C_CLAIM_LEDGER.yaml` mutation. Byte-exact sha256
  preservation verified in test
  `test_m2_does_not_modify_d002c_ledger`.
* No D-002G tier promotion. No `SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN` claim.
* No cross-promotion to D-002C. The D-002C ledger remains
  append-only at its attempt-2 falsification.
* No M1 removal. M1 stays primary for substrates where it is
  ELIGIBLE (`ricci_flow`).
* No threshold edit to any locked pre-registration constant
  (`null_seed_offset=10000`, `r2_b_random_site_seed=99`,
  `bonferroni_n_cells=216`, `R2B_FPR_THRESHOLD=0.05`).
* No node-payload / injection-sequence M2 sub-domain. Those
  shuffle domains are reserved by the `shuffle_domain` literal
  but not implemented; a future PR may extend them.
* No B1 full-CLOSURE. The blockers manifest reflects partial
  mitigation only.

## 10. SUBSTRATE ELIGIBILITY UNDER M2 (CANONICAL-RUN BLOCKER STATUS)

| Substrate id | M1 verdict | M2 (edge_weight) verdict | M1 ∪ M2 admissibility |
|---|---|---|---|
| `ricci_flow` | M1-ELIGIBLE | ELIGIBLE_M2 | ELIGIBLE under both — M1 primary |
| `block_structured` | M1-INELIGIBLE | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | NOT ADMISSIBLE — canonical D-002G run is BLOCKED on this substrate |
| `temporal_coupling` | M1-INELIGIBLE | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | NOT ADMISSIBLE — canonical D-002G run is BLOCKED on this substrate |

The canonical D-002G run is BLOCKED until a third mechanism (M2
node-payload sub-domain, M2 injection-sequence sub-domain, or a
fresh pre-registered M3..) admits the two constant-payload
substrates. Downstream PR tag: **D-002G-P3/M2-extension** or
**D-002G-P3/M3** depending on the chosen successor mechanism.
