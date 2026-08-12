# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth for geosync/proof/audit.py — the external-auditor claims gate.

A test that cannot fail is not a test. Each case asserts a way the auditor must refuse to
be fooled:
  * a fired falsifier MUST surface as REFUTED (never hidden);
  * a green rc with no passing junit MUST NOT launder into SUPPORTED;
  * an ANCHORED claim with no falsifier MUST be DANGLING;
  * a banned status phrase MUST be FORBIDDEN_LANGUAGE and dominate;
  * a single REJECT MUST sink the weakest-link aggregate and drive a nonzero exit;
  * an edited report MUST fail --verify.

Two families of teeth:
  1. FAST, deterministic unit teeth using dependency injection (resolve_fn/execute_fn/
     heavy_fn stubs) — no subprocess, so the decision table is pinned exactly.
  2. SLOW end-to-end teeth (marked ``slow``) that write a REAL failing/passing pytest node
     and let the auditor execute pytest itself — proving the whole pipeline (collect -> run
     -> junit cross-check) surfaces REFUTED/SUPPORTED, and a positive control proves the
     gate is a genuine discriminator, not stuck-red.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from geosync.proof import audit as A

FORBIDDEN_STUB = textwrap.dedent(
    """\
    # Forbidden Claims Contract

    ## Product Category Boundary

    Prose with a `live trading` backtick that MUST NOT be parsed as banned status language.

    ## Banned Status Language

    The following phrases are forbidden:

    - `validated alpha`
    - `guaranteed edge`
    - `proven predictor`

    ## Allowed Status Language

    | Status | Meaning |
    | --- | --- |
    | `Active` | implemented and checked |
    """
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _claims_yaml(tmp_path: Path, claims: list[dict]) -> Path:
    import yaml

    return _write(tmp_path / "CLAIMS.yaml", yaml.safe_dump({"schema_version": 3, "claims": claims}))


def _forbidden(tmp_path: Path) -> Path:
    return _write(tmp_path / "FORBIDDEN_CLAIMS.md", FORBIDDEN_STUB)


def _empty_allow(tmp_path: Path) -> Path:
    return _write(tmp_path / "allow.json", json.dumps({"allow": {}}))


def _report(tmp_path: Path, claims: list[dict], *, mode: str = A.MODE_RESOLVE, allow=None, **kw):
    """Build a report with STUBBED subprocess fns by default (no real pytest), unless the
    caller injects resolve_fn/execute_fn/heavy_fn."""
    return A.build_report(
        mode=mode,
        claims_path=_claims_yaml(tmp_path, claims),
        forbidden_path=_forbidden(tmp_path),
        allowlist_path=allow if allow is not None else _empty_allow(tmp_path),
        **kw,
    )


# --------------------------------------------------------------------------- #
# classify_execution: the honesty core (pure function, exhaustively pinned).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "rc, junit, allow, expect",
    [
        (0, "passed", False, A.SUPPORTED),      # the ONLY green path
        (1, "failure", False, A.REFUTED),       # falsifier fired
        (1, "passed", False, A.REFUTED),        # rc1 wins over a stale-passed junit
        (0, "failure", False, A.REFUTED),       # junit failure wins over green rc
        (0, "empty", False, A.DANGLING),        # rc0 + no junit MUST NOT launder to SUPPORTED
        (0, "skipped", False, A.DANGLING),      # silent skip = falsifier did not run
        (0, "skipped", True, A.NOT_TESTED),     # allowlisted optional-dep skip is honest
        (0, "error", False, A.DANGLING),        # collect/usage error
        (2, "passed", False, A.DANGLING),       # interrupted -> fail-closed
        (3, "passed", False, A.DANGLING),       # internal error -> fail-closed
        (None, "timeout", False, A.DANGLING),   # hang -> fail-closed, never SUPPORTED
    ],
)
def test_classify_execution_never_launders_a_pass(rc, junit, allow, expect) -> None:
    verdict, _ = A.classify_execution(rc, junit, allow)
    assert verdict == expect, (
        f"classify_execution(rc={rc}, junit={junit!r}, allow={allow}) -> {verdict}, "
        f"expected {expect}. SUPPORTED must require BOTH rc==0 AND junit=='passed'."
    )


def test_parse_junit_outcome_precedence() -> None:
    xml = (
        "<testsuite>"
        "<testcase name='a'><failure/></testcase>"
        "<testcase name='b'><skipped/></testcase>"
        "<testcase name='c'/>"
        "</testsuite>"
    )
    assert A.parse_junit_outcome(xml) == "failure"  # failure dominates
    assert A.parse_junit_outcome("<testsuite/>") == "empty"
    assert A.parse_junit_outcome("not xml <<<") == "empty"
    passing = "<testsuite><testcase name='ok'/></testsuite>"
    assert A.parse_junit_outcome(passing) == "passed"


# --------------------------------------------------------------------------- #
# Static-firewall + decision-table teeth (resolve-only mode: no execution).
# --------------------------------------------------------------------------- #
def test_banned_phrase_is_forbidden_language_and_dominates(tmp_path: Path) -> None:
    claims = [{
        "id": "c-banned", "priority": "P1", "tier": "ANCHORED",
        "description": "This ships a guaranteed edge on live venues.",
        "falsifier": {"test_id": "tests/does_not_matter.py::t"},
    }]
    rep = _report(tmp_path, claims)
    row = rep["claims"][0]
    assert row["verdict"] == A.FORBIDDEN_LANGUAGE, (
        f"banned phrase must be FORBIDDEN_LANGUAGE, got {row['verdict']} — a firewall that "
        f"lets 'guaranteed edge' through is decorative."
    )
    assert row["class"] == A.REJECT
    # firewall dominates before any compute: the falsifier was never resolved.
    assert row["collect_status"] is None


def test_banned_parser_ignores_allowed_table_and_boundary_prose(tmp_path: Path) -> None:
    banned = A.parse_banned_phrases(FORBIDDEN_STUB)
    assert "validated alpha" in banned and "proven predictor" in banned
    assert "active" not in banned          # from the Allowed Status Language table
    assert "live trading" not in banned    # from the Product Category Boundary prose


def test_anchored_without_falsifier_is_dangling(tmp_path: Path) -> None:
    claims = [{
        "id": "c-anchored-no-fals", "priority": "P0", "tier": "ANCHORED",
        "description": "A load-bearing invariant with no named falsifier.",
    }]
    rep = _report(tmp_path, claims)
    assert rep["claims"][0]["verdict"] == A.DANGLING, (
        "an ANCHORED claim MUST name a falsifier (Promotion-Invariant #2); absence is a "
        "broken contract, not a pass."
    )
    assert rep["aggregate"] == A.REJECT


def test_extrapolated_without_falsifier_is_not_tested_partial(tmp_path: Path) -> None:
    claims = [{
        "id": "c-extrap", "priority": "P1", "tier": "EXTRAPOLATED",
        "description": "Admissible-by-design partial claim, no falsifier yet.",
    }]
    rep = _report(tmp_path, claims)
    row = rep["claims"][0]
    assert row["verdict"] == A.NOT_TESTED and row["class"] == A.PARTIAL
    assert rep["aggregate"] == A.PARTIAL
    assert A.process_exit_code(rep["aggregate"], strict=False) == 0
    assert A.process_exit_code(rep["aggregate"], strict=True) == 1  # signoff refuses PARTIAL


def test_dangling_test_id_rejects_but_allowlisted_stays_partial(tmp_path: Path) -> None:
    tid = "tests/nonexistent_ghost.py::test_ghost"
    claims = [{
        "id": "c-ghost", "priority": "P0", "tier": "ANCHORED",
        "description": "Names a falsifier whose file does not exist.",
        "falsifier": {"test_id": tid},
    }]
    # not allowlisted -> DANGLING/REJECT
    rep = _report(tmp_path, claims)
    assert rep["claims"][0]["verdict"] == A.DANGLING
    assert rep["aggregate"] == A.REJECT
    # allowlisted optional-dep -> NOT_TESTED/PARTIAL (honest, mirrors check_falsifier_nodes)
    allow = _write(tmp_path / "allow2.json", json.dumps({"allow": {tid: "optional dep foo"}}))
    rep2 = _report(tmp_path, claims, allow=allow)
    assert rep2["claims"][0]["verdict"] == A.NOT_TESTED
    assert rep2["claims"][0]["allowlisted"] is True
    assert rep2["aggregate"] == A.PARTIAL


# --------------------------------------------------------------------------- #
# Dependency-injected execution teeth (deterministic, no real pytest).
# --------------------------------------------------------------------------- #
def test_injected_failing_falsifier_is_refuted(tmp_path: Path) -> None:
    claims = [{
        "id": "c-fires", "priority": "P0", "tier": "ANCHORED",
        "description": "A claim whose falsifier fails.",
        "falsifier": {"test_id": "tests/real.py::t"},
    }]
    rep = _report(
        tmp_path, claims, mode=A.MODE_DEFAULT,
        resolve_fn=lambda tid: (True, "collected"),
        heavy_fn=lambda tid: False,
        execute_fn=lambda tid, to: (1, "failure"),
    )
    row = rep["claims"][0]
    assert row["verdict"] == A.REFUTED, "a failing falsifier MUST be REFUTED, never hidden."
    assert rep["aggregate"] == A.REJECT
    assert A.process_exit_code(rep["aggregate"], strict=False) == 1


def test_injected_passing_falsifier_is_supported_positive_control(tmp_path: Path) -> None:
    claims = [{
        "id": "c-holds", "priority": "P0", "tier": "ANCHORED",
        "description": "A claim whose falsifier passes.",
        "falsifier": {"test_id": "tests/real.py::t"},
    }]
    rep = _report(
        tmp_path, claims, mode=A.MODE_DEFAULT,
        resolve_fn=lambda tid: (True, "collected"),
        heavy_fn=lambda tid: False,
        execute_fn=lambda tid, to: (0, "passed"),
    )
    assert rep["claims"][0]["verdict"] == A.SUPPORTED
    assert rep["aggregate"] == A.ACCEPT
    assert A.process_exit_code(rep["aggregate"], strict=True) == 0


def test_resolve_only_never_executes(tmp_path: Path) -> None:
    def _boom(tid, to):  # execute_fn must NOT be called in resolve-only mode
        raise AssertionError("resolve-only mode must not execute a node")

    claims = [{
        "id": "c-resolve", "priority": "P0", "tier": "ANCHORED",
        "description": "A claim whose falsifier collects.",
        "falsifier": {"test_id": "tests/real.py::t"},
    }]
    rep = _report(
        tmp_path, claims, mode=A.MODE_RESOLVE,
        resolve_fn=lambda tid: (True, "collected"),
        execute_fn=_boom,
    )
    row = rep["claims"][0]
    assert row["verdict"] == A.NOT_TESTED and row["class"] == A.PARTIAL
    assert row["run_rc"] is None, "resolve-only must not upgrade a collectible node to SUPPORTED"


def test_heavy_node_parked_in_default_but_run_in_deep(tmp_path: Path) -> None:
    calls: list[str] = []

    def _exec(tid, to):
        calls.append(tid)
        return (0, "passed")

    claims = [{
        "id": "c-heavy", "priority": "P1", "tier": "ANCHORED",
        "description": "A heavy-marked falsifier.",
        "falsifier": {"test_id": "tests/heavy.py::t"},
    }]
    common = dict(resolve_fn=lambda tid: (True, "collected"), heavy_fn=lambda tid: True, execute_fn=_exec)
    rep_def = _report(tmp_path, claims, mode=A.MODE_DEFAULT, **common)
    assert rep_def["claims"][0]["verdict"] == A.NOT_TESTED
    assert calls == [], "default mode must NOT execute a heavy node"
    rep_deep = _report(tmp_path, claims, mode=A.MODE_DEEP, **common)
    assert rep_deep["claims"][0]["verdict"] == A.SUPPORTED
    assert calls == ["tests/heavy.py::t"], "--deep MUST execute the heavy node"


# --------------------------------------------------------------------------- #
# Weakest-link + severity ordering.
# --------------------------------------------------------------------------- #
def test_one_reject_sinks_an_otherwise_clean_run(tmp_path: Path) -> None:
    claims = [
        {"id": "ok-1", "priority": "P1", "tier": "EXTRAPOLATED", "description": "fine"},
        {"id": "ok-2", "priority": "P1", "tier": "EXTRAPOLATED", "description": "fine too"},
        {"id": "bad", "priority": "P0", "tier": "ANCHORED",
         "description": "This is a guaranteed edge.",
         "falsifier": {"test_id": "tests/x.py::t"}},
    ]
    rep = _report(tmp_path, claims)
    assert rep["aggregate"] == A.REJECT, "a single bad claim must sink the whole run"
    # render_table sorts most-severe first: FORBIDDEN_LANGUAGE row is on top.
    top = A._sorted_rows(rep)[0]
    assert top["id"] == "bad" and top["verdict"] == A.FORBIDDEN_LANGUAGE
    assert A.process_exit_code(rep["aggregate"], strict=False) == 1


def test_aggregate_and_exit_matrix() -> None:
    assert A.aggregate_verdict([{"verdict": A.SUPPORTED}]) == A.ACCEPT
    assert A.aggregate_verdict([{"verdict": A.SUPPORTED}, {"verdict": A.NOT_TESTED}]) == A.PARTIAL
    assert A.aggregate_verdict([{"verdict": A.NOT_TESTED}, {"verdict": A.REFUTED}]) == A.REJECT
    assert A.process_exit_code(A.ACCEPT, strict=True) == 0
    assert A.process_exit_code(A.PARTIAL, strict=False) == 0
    assert A.process_exit_code(A.PARTIAL, strict=True) == 1
    assert A.process_exit_code(A.REJECT, strict=False) == 1


# --------------------------------------------------------------------------- #
# Provenance / tamper-evidence (reuses run.py digest helpers).
# --------------------------------------------------------------------------- #
def test_report_is_tamper_evident(tmp_path: Path) -> None:
    claims = [{"id": "x", "priority": "P1", "tier": "EXTRAPOLATED", "description": "fine"}]
    rep = _report(tmp_path, claims)
    out = tmp_path / "audit.json"
    A.write_report(rep, out)
    ok, problems = A.verify_report(out)
    assert ok, f"freshly written report must verify: {problems}"

    edited = json.loads(out.read_text())
    edited["aggregate"] = "ACCEPT"  # forge a greener verdict
    out.write_text(json.dumps(edited))
    ok2, problems2 = A.verify_report(out)
    assert not ok2 and any("content_digest" in p for p in problems2), (
        "an edited aggregate must fail --verify — the report must be un-forgeable after production."
    )


def test_provenance_fields_present_and_bound(tmp_path: Path) -> None:
    claims = [{"id": "x", "priority": "P1", "tier": "EXTRAPOLATED", "description": "fine"}]
    cpath = _claims_yaml(tmp_path, claims)
    fpath = _forbidden(tmp_path)
    rep = A.build_report(
        mode=A.MODE_RESOLVE, claims_path=cpath, forbidden_path=fpath,
        allowlist_path=_empty_allow(tmp_path),
    )
    assert rep["claims_sha256"] == A._sha256_file(cpath)
    assert rep["forbidden_sha256"] == A._sha256_file(fpath)
    assert rep["code_version"] == A._code_version()
    assert str(rep[A.DIGEST_KEY]).startswith("sha256:")
    assert "validated alpha" in rep["banned_phrases"]  # parsed live, not hardcoded


def test_verify_detects_swapped_policy_file(tmp_path: Path) -> None:
    """If the pinned claims file is edited after production, re-hashing must catch it."""
    claims = [{"id": "x", "priority": "P1", "tier": "EXTRAPOLATED", "description": "fine"}]
    cpath = _claims_yaml(tmp_path, claims)
    rep = A.build_report(
        mode=A.MODE_RESOLVE, claims_path=cpath, forbidden_path=_forbidden(tmp_path),
        allowlist_path=_empty_allow(tmp_path),
    )
    # point the report's claims_source at a repo-relative path, then verify against ROOT.
    out = tmp_path / "audit.json"
    A.write_report(rep, out)
    # tamper the claims file the report was hashed against.
    cpath.write_text(cpath.read_text() + "\n# sneaky edit\n", encoding="utf-8")
    # verify_report resolves claims_source relative to ROOT; the tmp path won't exist there,
    # so it reports a missing pinned file (still a refusal, never a silent OK).
    ok, problems = A.verify_report(out)
    assert not ok and problems, "verify must refuse when a pinned file cannot be re-hashed"


# --------------------------------------------------------------------------- #
# SLOW end-to-end teeth: the auditor RUNS real pytest itself.
# --------------------------------------------------------------------------- #
def _make_probe(passing: bool) -> tuple[str, Path]:
    """Write a REAL collectible pytest node under a non-testpaths dir inside ROOT and return
    (node_id, path). artifacts/ is not in pytest.ini testpaths, so this file is only ever
    collected via the explicit node id the auditor passes — no pollution of the repo suite.
    """
    d = A.ROOT / "artifacts" / "geosync_proof" / "_audit_selftest"
    d.mkdir(parents=True, exist_ok=True)
    name = "test_pass_probe.py" if passing else "test_fail_probe.py"
    body = (
        "def test_probe():\n    assert True\n" if passing
        else "def test_probe():\n    assert False, 'INV-SELFTEST falsifier FIRED'\n"
    )
    f = d / name
    f.write_text(body, encoding="utf-8")
    return f"{f.relative_to(A.ROOT).as_posix()}::test_probe", f


@pytest.mark.slow
def test_e2e_running_real_pytest_exposes_a_fired_falsifier(tmp_path: Path) -> None:
    tid, f = _make_probe(passing=False)
    try:
        claims = [{
            "id": "c-e2e-fires", "priority": "P0", "tier": "ANCHORED",
            "description": "A claim whose real falsifier actually fails.",
            "falsifier": {"test_id": tid},
        }]
        rep = A.build_report(
            mode=A.MODE_DEFAULT, per_test_timeout=120,
            claims_path=_claims_yaml(tmp_path, claims),
            forbidden_path=_forbidden(tmp_path),
            allowlist_path=_empty_allow(tmp_path),
        )
        row = rep["claims"][0]
        assert row["verdict"] == A.REFUTED, (
            f"a REAL failing falsifier MUST be REFUTED, got {row['verdict']} "
            f"(rc={row['run_rc']}, junit={row['junit_outcome']})."
        )
        assert row["junit_outcome"] == "failure" and row["run_rc"] == 1
        assert rep["aggregate"] == A.REJECT
    finally:
        f.unlink(missing_ok=True)


@pytest.mark.slow
def test_e2e_running_real_pytest_supports_a_passing_falsifier(tmp_path: Path) -> None:
    tid, f = _make_probe(passing=True)
    try:
        claims = [{
            "id": "c-e2e-holds", "priority": "P0", "tier": "ANCHORED",
            "description": "A claim whose real falsifier passes.",
            "falsifier": {"test_id": tid},
        }]
        rep = A.build_report(
            mode=A.MODE_DEFAULT, per_test_timeout=120,
            claims_path=_claims_yaml(tmp_path, claims),
            forbidden_path=_forbidden(tmp_path),
            allowlist_path=_empty_allow(tmp_path),
        )
        row = rep["claims"][0]
        assert row["verdict"] == A.SUPPORTED, (
            f"a REAL passing falsifier should be SUPPORTED, got {row['verdict']} — "
            f"positive control proves the REFUTED result is a genuine discriminator."
        )
        assert row["run_rc"] == 0 and row["junit_outcome"] == "passed"
        assert rep["aggregate"] == A.ACCEPT
    finally:
        f.unlink(missing_ok=True)


@pytest.mark.slow
def test_cli_resolve_only_over_real_repo_claims() -> None:
    """End-to-end CLI on the REAL 27 claims (fast --resolve-only): emits the summary line,
    writes the artifact, and the artifact self-verifies."""
    r = subprocess.run(
        [sys.executable, "-m", "geosync.proof.audit", "--resolve-only"],
        cwd=A.ROOT, capture_output=True, text=True, timeout=600,
    )
    assert r.returncode in (0, 1), f"unexpected rc={r.returncode}: {r.stderr[-400:]}"
    assert "GEOSYNC_AUDIT " in r.stdout
    assert "aggregate=" in r.stdout and "claims=" in r.stdout
    assert A.ARTIFACT.exists(), "CLI must write artifacts/geosync_proof/audit.json"
    report = json.loads(A.ARTIFACT.read_text())
    assert report["claim_count"] >= 1
    ok, problems = A.verify_report(A.ARTIFACT)
    assert ok, f"the artifact the CLI just wrote must self-verify: {problems}"