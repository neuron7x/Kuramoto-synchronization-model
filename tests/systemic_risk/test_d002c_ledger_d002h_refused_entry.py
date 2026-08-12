# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C claim ledger -- D-002H REFUSED append-only entry contract.

The D-002C claim ledger at ``docs/governance/D002C_CLAIM_LEDGER.yaml``
records the scoped scientific verdicts of the D-002C / D-002H lineage.
Until this PR it carried exactly two entries (attempt-1 SUPPORTED +
attempt-2 FALSIFIED). This PR is the FIRST legitimate append after
sixteen byte-exact preservation PRs; it adds a third entry recording
the D-002H ricci_flow scoped REFUSED verdict produced by the canonical
sweep merged at PR #691 (sha 250d8069...).

These tests pin:

  * the ledger parses as YAML and carries exactly 3 claim entries;
  * the first two entries are byte-exact unchanged (claim_id, status,
    eclipses chain, key supporting fields) -- pre-existing ledger
    history is APPEND-ONLY by construction;
  * the third entry (NEW) carries claim_id, status, tier, scope,
    eclipses=None (NOT an eclipse -- D-002H is a separate SCOPED
    lineage opened after D-002G structural closure), the locked
    canonical-run anchor SHA, the canonical grid byte-equivalent to
    the D-002H prereg block, the 2-mechanism null set, the
    NULL_AUDIT_FAIL anti-overclaim guard, the post-sweep null audit
    FAIL aggregate, and all seven gate authorisation anchor SHAs;
  * the D-002G prereg, D-002G P3 M3 prereg, D-002G acceptance rules,
    D-002H prereg, and D-002H R2-B note SHAs are unchanged.

Lessons applied:
  * L1 -- N/A (no Python source symbols introduced).
  * L2 -- pinned sha values carry ``# pragma: allowlist secret`` to
    bypass detect-secrets HexHighEntropy false-positives.
  * L3 -- every assertion has a descriptive ``msg_*`` variable.
  * L4 -- every test has >= 2 assertions or >= 2 distinct cases.
  * L5 -- zero broad-except in this file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

LEDGER_RELPATH = "docs/governance/D002C_CLAIM_LEDGER.yaml"
LEDGER_PATH = REPO_ROOT / LEDGER_RELPATH

D002G_PREREG_RELPATH = "docs/governance/D002G_PREREGISTRATION.yaml"
D002G_P3_M3_PREREG_RELPATH = "docs/governance/D002G_P3_M3_PREREGISTRATION.md"
D002G_ACCEPTANCE_RELPATH = "docs/governance/D002G_ACCEPTANCE_RULES.md"
D002H_PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"
R2B_NOTE_RELPATH = "docs/governance/D002H_R2B_INAPPLICABILITY_NOTE.md"

# fmt: off
D002G_PREREG_SHA_PIN: str = "1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04"  # noqa: E501  # pragma: allowlist secret
D002G_P3_M3_PREREG_SHA_PIN: str = "0f11a0c890374c35e4dedecc66caec52ae867f49a8f8b3be2374f1464712c1f8"  # noqa: E501  # pragma: allowlist secret
D002G_ACCEPTANCE_SHA_PIN: str = "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31"  # noqa: E501  # pragma: allowlist secret
D002H_PREREG_SHA_PIN: str = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # noqa: E501  # pragma: allowlist secret
R2B_NOTE_SHA_PIN: str = "e76196ecc47ecc85fc42ceb12c1e3df604d3663bfbdb5b58561172149334db34"  # noqa: E501  # pragma: allowlist secret

CANONICAL_RUN_MERGE_SHA: str = "250d8069d16ecabdb49b5a20b7cf1d622eddc925"  # noqa: E501  # pragma: allowlist secret
PARENT_CLOSURE_SHA: str = "8cf5364a3f3b605d8b134bccbfe5170098e0e197"  # noqa: E501  # pragma: allowlist secret
R2B_CLARIFICATION_ANCHOR: str = "ee12a9e6a08e5916109c99eec84796d1e1375cd0"  # noqa: E501  # pragma: allowlist secret

GATE_A_ANCHOR: str = "1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5"  # noqa: E501  # pragma: allowlist secret
GATE_B_ANCHOR: str = "b97daae8b554ab9960510564e19263adcc1fe71b"  # noqa: E501  # pragma: allowlist secret
GATE_C_ANCHOR: str = "a9d852d34258861809325df81bd7cba6d0e557ec"  # noqa: E501  # pragma: allowlist secret
GATE_D_ANCHOR: str = "077073ee801c434840d64f911e7b1f39ce2ac0fa"  # noqa: E501  # pragma: allowlist secret
GATE_E_ANCHOR: str = "e1d3ae304274e8b8f509edeb83b0a9adfeb43a77"  # noqa: E501  # pragma: allowlist secret
GATE_F_ANCHOR: str = "0e598fff84308356fd93e953d4fdde0b7811ac53"  # noqa: E501  # pragma: allowlist secret
GATE_G_ANCHOR: str = "4686455ed8de3902ea5ad4040bfc4ca8c530bc39"  # noqa: E501  # pragma: allowlist secret
# fmt: on

EXPECTED_N_CLAIMS = 3

ENTRY_1_CLAIM_ID = "D002C_CANONICAL_SYNTHETIC_PASS_SYNC_AUC"
ENTRY_1_STATUS = "SUPPORTED_SYNTHETIC_SCOPED"
ENTRY_1_TIER = "SYNTHETIC_GATE6_CERTIFIED_REDESIGN_N_LE_200"
ENTRY_1_RUN_ID = "d002c_canonical_20260512T122837Z"

ENTRY_2_CLAIM_ID = "D002C_CANONICAL_SYNTHETIC_ATTEMPT_2_FALSIFIED"
ENTRY_2_STATUS = "FALSIFIED_BY_EXECUTABLE_NULL_AUDIT"
ENTRY_2_TIER = "D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET"
ENTRY_2_ECLIPSES = "D002C_CANONICAL_SYNTHETIC_PASS_SYNC_AUC"
ENTRY_2_RUN_ID = "d002c_canonical_attempt_2_20260512T160318Z"

ENTRY_3_CLAIM_ID = "D002H_RICCI_FLOW_SCOPED_REFUSED"
ENTRY_3_STATUS = "REFUSED_BY_NULL_AUDIT_FAIL"
ENTRY_3_TIER = "REFUSED_NULL_AUDIT_FAIL_D002H"
ENTRY_3_PARENT_LINEAGE = "D-002H"
ENTRY_3_PARENT_CLOSURE_ARTIFACT = "D-002G_STRUCTURAL_CLOSURE_PR682"

EXPECTED_CANONICAL_GRID_SUBSTRATES = ["ricci_flow"]
EXPECTED_CANONICAL_GRID_N = [50, 100, 200]
EXPECTED_CANONICAL_GRID_LAMBDA = [0.0, 0.05, 0.10, 0.20, 0.40, 1.0]
EXPECTED_CANONICAL_GRID_N_SEEDS = 20
EXPECTED_CANONICAL_GRID_N_BOOTSTRAP = 16
EXPECTED_CANONICAL_GRID_TOTAL_CELLS = 18

EXPECTED_NULL_MECHANISMS = ["M1_INDEPENDENT_SEED", "M3_TOPOLOGY_CONDITIONED"]
FORBIDDEN_NULL_MECHANISM_M6 = "M6_PLACEBO_COUPLING"

EXPECTED_NULL_AUDIT_VERDICT = "FAIL"
EXPECTED_NULL_AUDIT_N_AUDITED = 54
EXPECTED_NULL_AUDIT_N_PASS = 12
EXPECTED_NULL_AUDIT_N_FAIL = 42
EXPECTED_NULL_AUDIT_N_SHUFFLES = 100
EXPECTED_NULL_AUDIT_RNG_SEED = 42

EXPECTED_N_CELLS_TOTAL = 18
EXPECTED_N_CELLS_PASS = 0
EXPECTED_N_CELLS_FAIL = 15
EXPECTED_N_CELLS_INDETERMINATE = 3

EXPECTED_ARTIFACT_PATH = "artifacts/d002h/canonical/d002h_canonical_run_verdict.json"
EXPECTED_ANTI_OVERCLAIM_GUARDS = ["NULL_AUDIT_FAIL"]

EXPECTED_GATE_ANCHORS = {
    "gate_a_anchor": GATE_A_ANCHOR,
    "gate_b_anchor": GATE_B_ANCHOR,
    "gate_c_anchor": GATE_C_ANCHOR,
    "gate_d_anchor": GATE_D_ANCHOR,
    "gate_e_anchor": GATE_E_ANCHOR,
    "gate_f_anchor": GATE_F_ANCHOR,
    "gate_g_anchor": GATE_G_ANCHOR,
}


def _load_ledger() -> dict[str, Any]:
    """Parse the D-002C claim ledger as YAML."""
    raw = LEDGER_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    if not isinstance(parsed, dict):
        raise AssertionError(
            f"D-002C claim ledger root must be a mapping; got {type(parsed).__name__}"
        )
    return cast(dict[str, Any], parsed)


def _load_claims() -> list[dict[str, Any]]:
    """Return the ``claims`` list of the ledger as a list of mappings."""
    data = _load_ledger()
    if "claims" not in data:
        raise AssertionError("D-002C claim ledger missing 'claims' key")
    claims = data["claims"]
    if not isinstance(claims, list):
        raise AssertionError(
            f"D-002C claim ledger 'claims' must be a list; got {type(claims).__name__}"
        )
    typed: list[dict[str, Any]] = []
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            raise AssertionError(f"claims[{i}] must be a mapping; got {type(c).__name__}")
        typed.append(cast(dict[str, Any], c))
    return typed


def _sha256_of(rel: str) -> str:
    """Return the lowercase hex sha256 of a repo-relative file."""
    path = REPO_ROOT / rel
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def test_ledger_parses_as_yaml_and_has_claims_key() -> None:
    """The D-002C claim ledger is valid YAML carrying a 'claims' list."""
    data = _load_ledger()
    claims = data.get("claims")

    msg_has_claims = "D-002C ledger must carry top-level 'claims' key (YAML schema invariant)"
    assert "claims" in data, msg_has_claims

    msg_is_list = (
        f"'claims' must be a YAML sequence (list of claim entries); got {type(claims).__name__}"
    )
    assert isinstance(claims, list), msg_is_list


def test_ledger_carries_exactly_three_claim_entries() -> None:
    """Append-only contract -- exactly 3 entries after this PR (was 2)."""
    claims = _load_claims()

    msg_count = (
        f"D-002C ledger must carry exactly {EXPECTED_N_CLAIMS} entries "
        f"(2 D-002C historical + 1 new D-002H REFUSED); got {len(claims)}"
    )
    assert len(claims) == EXPECTED_N_CLAIMS, msg_count

    claim_ids = [c["claim_id"] for c in claims]
    msg_unique = f"all claim_ids must be unique; got duplicates in {claim_ids}"
    assert len(set(claim_ids)) == EXPECTED_N_CLAIMS, msg_unique


def test_entry_1_attempt_1_supported_byte_exact_invariants() -> None:
    """Entry [0] (attempt-1 SUPPORTED) preserved byte-exact at key fields."""
    claims = _load_claims()
    entry = claims[0]

    msg_claim_id = (
        f"entry[0] claim_id must be '{ENTRY_1_CLAIM_ID}' (D-002C attempt-1 "
        f"historical defensible PASS); got '{entry.get('claim_id')}'"
    )
    assert entry.get("claim_id") == ENTRY_1_CLAIM_ID, msg_claim_id

    msg_status = f"entry[0] status must be '{ENTRY_1_STATUS}'; got '{entry.get('status')}'"
    assert entry.get("status") == ENTRY_1_STATUS, msg_status

    msg_tier = f"entry[0] tier must be '{ENTRY_1_TIER}'; got '{entry.get('tier')}'"
    assert entry.get("tier") == ENTRY_1_TIER, msg_tier

    msg_run_id = f"entry[0] run_id must be '{ENTRY_1_RUN_ID}'; got '{entry.get('run_id')}'"
    assert entry.get("run_id") == ENTRY_1_RUN_ID, msg_run_id


def test_entry_2_attempt_2_falsified_eclipses_attempt_1() -> None:
    """Entry [1] (attempt-2 FALSIFIED) eclipses entry [0] and is byte-exact."""
    claims = _load_claims()
    entry = claims[1]

    msg_claim_id = (
        f"entry[1] claim_id must be '{ENTRY_2_CLAIM_ID}' (D-002C attempt-2 "
        f"executable null-audit falsification); got '{entry.get('claim_id')}'"
    )
    assert entry.get("claim_id") == ENTRY_2_CLAIM_ID, msg_claim_id

    msg_status = f"entry[1] status must be '{ENTRY_2_STATUS}'; got '{entry.get('status')}'"
    assert entry.get("status") == ENTRY_2_STATUS, msg_status

    msg_tier = f"entry[1] tier must be '{ENTRY_2_TIER}'; got '{entry.get('tier')}'"
    assert entry.get("tier") == ENTRY_2_TIER, msg_tier

    msg_eclipses = (
        f"entry[1] eclipses must be '{ENTRY_2_ECLIPSES}' (attempt-2 supersedes "
        f"attempt-1 going forward); got '{entry.get('eclipses')}'"
    )
    assert entry.get("eclipses") == ENTRY_2_ECLIPSES, msg_eclipses

    msg_run_id = f"entry[1] run_id must be '{ENTRY_2_RUN_ID}'; got '{entry.get('run_id')}'"
    assert entry.get("run_id") == ENTRY_2_RUN_ID, msg_run_id


def test_entry_3_d002h_refused_core_fields() -> None:
    """Entry [2] (NEW) records D-002H ricci_flow scoped REFUSED verdict."""
    claims = _load_claims()
    entry = claims[2]

    msg_claim_id = (
        f"entry[2] claim_id must be '{ENTRY_3_CLAIM_ID}' (new D-002H scoped "
        f"REFUSED entry); got '{entry.get('claim_id')}'"
    )
    assert entry.get("claim_id") == ENTRY_3_CLAIM_ID, msg_claim_id

    msg_status = (
        f"entry[2] status must be '{ENTRY_3_STATUS}' (the post-sweep "
        f"permutation null audit FAILED at 42/54 audited cells); "
        f"got '{entry.get('status')}'"
    )
    assert entry.get("status") == ENTRY_3_STATUS, msg_status

    msg_tier = (
        f"entry[2] tier must be '{ENTRY_3_TIER}' (locked tier-string for "
        f"NULL_AUDIT_FAIL on D-002H); got '{entry.get('tier')}'"
    )
    assert entry.get("tier") == ENTRY_3_TIER, msg_tier

    scope = entry.get("scope")
    msg_scope = (
        f"entry[2] scope must mention 'ricci_flow' (substrate scope per "
        f"D-002H prereg); got '{scope}'"
    )
    assert isinstance(scope, str), msg_scope
    assert "ricci_flow" in scope, msg_scope


def test_entry_3_d002h_is_not_an_eclipse() -> None:
    """Entry [2] must carry eclipses=None -- D-002H is a SEPARATE lineage."""
    claims = _load_claims()
    entry = claims[2]

    msg_eclipses_null = (
        "entry[2] eclipses MUST be null/None -- D-002H is a new SCOPED "
        "lineage opened AFTER D-002G structural closure (PR #682); it does "
        f"NOT supersede D-002C attempt-1 or attempt-2; got '{entry.get('eclipses')!r}'"
    )
    assert entry.get("eclipses") is None, msg_eclipses_null

    msg_parent_lineage = (
        f"entry[2] parent_lineage must be '{ENTRY_3_PARENT_LINEAGE}'; "
        f"got '{entry.get('parent_lineage')}'"
    )
    assert entry.get("parent_lineage") == ENTRY_3_PARENT_LINEAGE, msg_parent_lineage

    actual_closure = entry.get("parent_closure_artifact")
    msg_parent_closure = (
        f"entry[2] parent_closure_artifact must be "
        f"'{ENTRY_3_PARENT_CLOSURE_ARTIFACT}'; got '{actual_closure}'"
    )
    assert actual_closure == ENTRY_3_PARENT_CLOSURE_ARTIFACT, msg_parent_closure


def test_entry_3_d002h_canonical_run_anchor_shas() -> None:
    """Entry [2] pins the PR #691 merge sha + parent closure + R2-B anchor."""
    claims = _load_claims()
    entry = claims[2]

    msg_merge = (
        f"entry[2] canonical_run_merge_sha must be PR #691 merge sha "
        f"'{CANONICAL_RUN_MERGE_SHA}'; got '{entry.get('canonical_run_merge_sha')}'"
    )
    assert entry.get("canonical_run_merge_sha") == CANONICAL_RUN_MERGE_SHA, msg_merge

    msg_pr = (
        f"entry[2] canonical_run_pr must be 691 (the canonical D-002H "
        f"sweep PR); got {entry.get('canonical_run_pr')!r}"
    )
    assert entry.get("canonical_run_pr") == 691, msg_pr

    msg_prereg = (
        f"entry[2] parent_lineage_prereg_sha must be the locked D-002H "
        f"prereg sha '{D002H_PREREG_SHA_PIN}'; "
        f"got '{entry.get('parent_lineage_prereg_sha')}'"
    )
    assert entry.get("parent_lineage_prereg_sha") == D002H_PREREG_SHA_PIN, msg_prereg

    msg_closure = (
        f"entry[2] parent_closure_sha must be PR #682 sha "
        f"'{PARENT_CLOSURE_SHA}'; got '{entry.get('parent_closure_sha')}'"
    )
    assert entry.get("parent_closure_sha") == PARENT_CLOSURE_SHA, msg_closure


def test_entry_3_d002h_canonical_grid_byte_equivalent_to_prereg() -> None:
    """Entry [2] canonical_grid mirrors the D-002H prereg grid block."""
    claims = _load_claims()
    entry = claims[2]

    grid = entry.get("canonical_grid")
    msg_grid_dict = f"entry[2] canonical_grid must be a mapping; got {type(grid).__name__}"
    assert isinstance(grid, dict), msg_grid_dict

    msg_substrates = (
        f"canonical_grid.substrates must be {EXPECTED_CANONICAL_GRID_SUBSTRATES} "
        f"(D-002H is ricci_flow-only); got {grid.get('substrates')!r}"
    )
    assert grid.get("substrates") == EXPECTED_CANONICAL_GRID_SUBSTRATES, msg_substrates

    msg_N = f"canonical_grid.N must be {EXPECTED_CANONICAL_GRID_N}; got {grid.get('N')!r}"
    assert grid.get("N") == EXPECTED_CANONICAL_GRID_N, msg_N

    msg_lambda = (
        f"canonical_grid.lambda_values must be {EXPECTED_CANONICAL_GRID_LAMBDA}; "
        f"got {grid.get('lambda_values')!r}"
    )
    assert grid.get("lambda_values") == EXPECTED_CANONICAL_GRID_LAMBDA, msg_lambda

    msg_seeds = (
        f"canonical_grid.n_seeds must be {EXPECTED_CANONICAL_GRID_N_SEEDS}; "
        f"got {grid.get('n_seeds')!r}"
    )
    assert grid.get("n_seeds") == EXPECTED_CANONICAL_GRID_N_SEEDS, msg_seeds

    msg_boot = (
        f"canonical_grid.n_bootstrap must be {EXPECTED_CANONICAL_GRID_N_BOOTSTRAP}; "
        f"got {grid.get('n_bootstrap')!r}"
    )
    assert grid.get("n_bootstrap") == EXPECTED_CANONICAL_GRID_N_BOOTSTRAP, msg_boot

    msg_total = (
        f"canonical_grid.total_cells must be {EXPECTED_CANONICAL_GRID_TOTAL_CELLS} "
        f"(3 N x 6 lambda x 1 substrate); got {grid.get('total_cells')!r}"
    )
    assert grid.get("total_cells") == EXPECTED_CANONICAL_GRID_TOTAL_CELLS, msg_total


def test_entry_3_d002h_null_mechanisms_m1_m3_only_not_m6() -> None:
    """Entry [2] null mechanisms must be M1 + M3 (M6 structurally excluded)."""
    claims = _load_claims()
    entry = claims[2]

    mechs = entry.get("null_mechanisms_used")
    msg_list = f"null_mechanisms_used must be a list; got {type(mechs).__name__}"
    assert isinstance(mechs, list), msg_list

    msg_mechs = (
        f"null_mechanisms_used must equal {EXPECTED_NULL_MECHANISMS} "
        f"(per D-002H prereg null_mechanisms_allowed); got {mechs!r}"
    )
    assert mechs == EXPECTED_NULL_MECHANISMS, msg_mechs

    msg_no_m6 = (
        f"null_mechanisms_used must NOT contain '{FORBIDDEN_NULL_MECHANISM_M6}' "
        f"(M6 is structurally excluded from D-002H per prereg; "
        f"R2-B is INAPPLICABLE per merge ee12a9e6); got {mechs!r}"
    )
    assert FORBIDDEN_NULL_MECHANISM_M6 not in mechs, msg_no_m6


def test_entry_3_d002h_post_sweep_null_audit_fail_aggregate() -> None:
    """Entry [2] records the post-sweep null audit FAIL aggregate verdict."""
    claims = _load_claims()
    entry = claims[2]

    audit = entry.get("post_sweep_null_audit")
    msg_dict = f"post_sweep_null_audit must be a mapping; got {type(audit).__name__}"
    assert isinstance(audit, dict), msg_dict

    msg_verdict = (
        f"post_sweep_null_audit.aggregate_verdict must be "
        f"'{EXPECTED_NULL_AUDIT_VERDICT}' (this is the source of the "
        f"NULL_AUDIT_FAIL anti-overclaim guard); "
        f"got '{audit.get('aggregate_verdict')}'"
    )
    assert audit.get("aggregate_verdict") == EXPECTED_NULL_AUDIT_VERDICT, msg_verdict

    msg_n_audited = (
        f"post_sweep_null_audit.n_audited must be {EXPECTED_NULL_AUDIT_N_AUDITED}; "
        f"got {audit.get('n_audited')!r}"
    )
    assert audit.get("n_audited") == EXPECTED_NULL_AUDIT_N_AUDITED, msg_n_audited

    msg_n_pass = (
        f"post_sweep_null_audit.n_pass must be {EXPECTED_NULL_AUDIT_N_PASS}; "
        f"got {audit.get('n_pass')!r}"
    )
    assert audit.get("n_pass") == EXPECTED_NULL_AUDIT_N_PASS, msg_n_pass

    msg_n_fail = (
        f"post_sweep_null_audit.n_fail must be {EXPECTED_NULL_AUDIT_N_FAIL}; "
        f"got {audit.get('n_fail')!r}"
    )
    assert audit.get("n_fail") == EXPECTED_NULL_AUDIT_N_FAIL, msg_n_fail

    n_pass_plus_fail = audit.get("n_pass", 0) + audit.get("n_fail", 0)
    msg_pass_plus_fail = (
        f"n_pass + n_fail must equal n_audited ({EXPECTED_NULL_AUDIT_N_AUDITED}); "
        f"got {audit.get('n_pass')} + {audit.get('n_fail')}"
    )
    assert n_pass_plus_fail == EXPECTED_NULL_AUDIT_N_AUDITED, msg_pass_plus_fail

    msg_shuffles = (
        f"post_sweep_null_audit.n_shuffles must be "
        f"{EXPECTED_NULL_AUDIT_N_SHUFFLES}; got {audit.get('n_shuffles')!r}"
    )
    assert audit.get("n_shuffles") == EXPECTED_NULL_AUDIT_N_SHUFFLES, msg_shuffles

    msg_seed = (
        f"post_sweep_null_audit.rng_seed must be {EXPECTED_NULL_AUDIT_RNG_SEED}; "
        f"got {audit.get('rng_seed')!r}"
    )
    assert audit.get("rng_seed") == EXPECTED_NULL_AUDIT_RNG_SEED, msg_seed


def test_entry_3_d002h_cell_breakdown_consistent() -> None:
    """Entry [2] per-cell breakdown sums to the canonical total (18)."""
    claims = _load_claims()
    entry = claims[2]

    msg_total = (
        f"entry[2] n_cells_total must be {EXPECTED_N_CELLS_TOTAL}; "
        f"got {entry.get('n_cells_total')!r}"
    )
    assert entry.get("n_cells_total") == EXPECTED_N_CELLS_TOTAL, msg_total

    msg_pass = (
        f"entry[2] n_cells_pass must be {EXPECTED_N_CELLS_PASS} (no cell "
        f"satisfied the 4-term conjunction); got {entry.get('n_cells_pass')!r}"
    )
    assert entry.get("n_cells_pass") == EXPECTED_N_CELLS_PASS, msg_pass

    msg_fail = (
        f"entry[2] n_cells_fail must be {EXPECTED_N_CELLS_FAIL}; got {entry.get('n_cells_fail')!r}"
    )
    assert entry.get("n_cells_fail") == EXPECTED_N_CELLS_FAIL, msg_fail

    msg_indet = (
        f"entry[2] n_cells_indeterminate must be "
        f"{EXPECTED_N_CELLS_INDETERMINATE}; got {entry.get('n_cells_indeterminate')!r}"
    )
    assert entry.get("n_cells_indeterminate") == EXPECTED_N_CELLS_INDETERMINATE, msg_indet

    sum_cells = (
        entry.get("n_cells_pass", 0)
        + entry.get("n_cells_fail", 0)
        + entry.get("n_cells_indeterminate", 0)
    )
    msg_sum = (
        f"n_cells_pass + n_cells_fail + n_cells_indeterminate must equal "
        f"n_cells_total ({EXPECTED_N_CELLS_TOTAL}); got {sum_cells}"
    )
    assert sum_cells == EXPECTED_N_CELLS_TOTAL, msg_sum


def test_entry_3_d002h_anti_overclaim_guards_artifact_path() -> None:
    """Entry [2] triggers NULL_AUDIT_FAIL guard and pins the verdict artifact."""
    claims = _load_claims()
    entry = claims[2]

    guards = entry.get("anti_overclaim_guards_triggered")
    msg_guards_list = f"anti_overclaim_guards_triggered must be a list; got {type(guards).__name__}"
    assert isinstance(guards, list), msg_guards_list

    msg_guards = (
        f"anti_overclaim_guards_triggered must equal "
        f"{EXPECTED_ANTI_OVERCLAIM_GUARDS}; got {guards!r}"
    )
    assert guards == EXPECTED_ANTI_OVERCLAIM_GUARDS, msg_guards

    msg_artifact = (
        f"entry[2] artifact_path must be '{EXPECTED_ARTIFACT_PATH}'; "
        f"got '{entry.get('artifact_path')}'"
    )
    assert entry.get("artifact_path") == EXPECTED_ARTIFACT_PATH, msg_artifact


def test_entry_3_d002h_seven_gate_authorisation_anchors() -> None:
    """Entry [2] records all 7 gate authorisation anchors + R2-B clarification."""
    claims = _load_claims()
    entry = claims[2]

    auth = entry.get("seven_gate_authorisation")
    msg_dict = f"seven_gate_authorisation must be a mapping; got {type(auth).__name__}"
    assert isinstance(auth, dict), msg_dict

    for gate_key, expected_sha in EXPECTED_GATE_ANCHORS.items():
        actual = auth.get(gate_key)
        msg_anchor = f"seven_gate_authorisation.{gate_key} must be '{expected_sha}'; got '{actual}'"
        assert actual == expected_sha, msg_anchor

    msg_r2b = (
        f"seven_gate_authorisation.r2b_clarification_anchor must be "
        f"'{R2B_CLARIFICATION_ANCHOR}' (merge ee12a9e6 for R2-B "
        f"inapplicability note); got '{auth.get('r2b_clarification_anchor')}'"
    )
    assert auth.get("r2b_clarification_anchor") == R2B_CLARIFICATION_ANCHOR, msg_r2b


def test_entry_3_d002h_acceptance_conjunction_and_notes() -> None:
    """Entry [2] records the 4-term conjunction and SCOPED-not-eclipse notes."""
    claims = _load_claims()
    entry = claims[2]

    conj = entry.get("acceptance_conjunction")
    msg_conj_str = f"acceptance_conjunction must be a string; got {type(conj).__name__}"
    assert isinstance(conj, str), msg_conj_str

    msg_r1 = "acceptance_conjunction must mention R1"
    assert "R1" in conj, msg_r1
    msg_r2 = "acceptance_conjunction must mention R2"
    assert "R2" in conj, msg_r2
    msg_r3 = "acceptance_conjunction must mention R3"
    assert "R3" in conj, msg_r3
    msg_audit = "acceptance_conjunction must mention NULL_AUDIT"
    assert "NULL_AUDIT" in conj, msg_audit
    msg_r2b_inapp = "acceptance_conjunction must mention R2-B INAPPLICABLE per D-002H"
    assert "R2-B" in conj and "INAPPLICABLE" in conj, msg_r2b_inapp

    notes = entry.get("notes")
    msg_notes_str = f"notes must be a string; got {type(notes).__name__}"
    assert isinstance(notes, str), msg_notes_str

    msg_scoped = (
        "notes must clarify the verdict is SCOPED to ricci_flow and does "
        "NOT generalise (truthful scope preservation)"
    )
    assert "ricci_flow" in notes and "block_structured" in notes, msg_scoped

    msg_no_change = (
        "notes must clarify that D-002C attempt-1 SUPPORTED and attempt-2 "
        "FALSIFIED entries are byte-exact above"
    )
    assert "SUPPORTED" in notes and "FALSIFIED" in notes, msg_no_change


def test_locked_governance_shas_unchanged() -> None:
    """D-002G prereg, P3 M3 prereg, acceptance rules, D-002H prereg, R2-B note."""
    msg_g_prereg = f"D-002G prereg sha256 must be locked at '{D002G_PREREG_SHA_PIN}'"
    assert _sha256_of(D002G_PREREG_RELPATH) == D002G_PREREG_SHA_PIN, msg_g_prereg

    msg_g_p3_m3 = f"D-002G P3 M3 prereg sha256 must be locked at '{D002G_P3_M3_PREREG_SHA_PIN}'"
    assert _sha256_of(D002G_P3_M3_PREREG_RELPATH) == D002G_P3_M3_PREREG_SHA_PIN, msg_g_p3_m3

    msg_accept = f"D-002G acceptance rules sha256 must be locked at '{D002G_ACCEPTANCE_SHA_PIN}'"
    assert _sha256_of(D002G_ACCEPTANCE_RELPATH) == D002G_ACCEPTANCE_SHA_PIN, msg_accept

    msg_h_prereg = f"D-002H prereg sha256 must be locked at '{D002H_PREREG_SHA_PIN}'"
    assert _sha256_of(D002H_PREREG_RELPATH) == D002H_PREREG_SHA_PIN, msg_h_prereg

    msg_r2b_note = f"D-002H R2-B inapplicability note sha256 must be locked at '{R2B_NOTE_SHA_PIN}'"
    assert _sha256_of(R2B_NOTE_RELPATH) == R2B_NOTE_SHA_PIN, msg_r2b_note
