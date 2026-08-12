# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the diff-bound commit acceptor validator.

Covers all 41 contract probes (schema, diff binding, AST imports,
evidence hashing, JSON determinism, idempotence).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.commit_acceptor.validate_commit_acceptor import (
    REQUIRED_TOP_LEVEL,
    RequiredFields,
    ValidationResult,
    compute_artifact_hashes,
    forbidden_imports,
    main,
    validate_acceptors,
    validate_diff_binding,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

POLICY: dict[str, Any] = {
    "version": 1,
    "code_file_extensions": [".py", ".yaml", ".yml", ".toml", ".json", ".sh"],
    "governance_markdown_paths": [".claude/", "docs/governance/", "docs/architecture/"],
    "max_changed_files_by_claim_type": {
        "correctness": 12,
        "determinism": 12,
        "fail_closed": 12,
        "security": 10,
        "performance": 10,
        "governance": 16,
        "refactor": 20,
        "documentation": 24,
    },
    "forbidden_import_patterns": ["trading", "execution", "forecast", "policy"],
    "dep_manifest_paths": ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
}


def _valid_acceptor(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "demo",
        "status": "ACTIVE",
        "claim_type": "governance",
        "promise": "Demo promise.",
        "diff_scope": {
            "changed_files": [{"path": "src/demo.py"}],
            "forbidden_paths": ["trading/", "execution/"],
        },
        "required_python_symbols": ["demo"],
        "expected_signal": "demo passes",
        "measurement_command": "pytest -k demo",
        "signal_artifact": "tmp/demo.log",
        "falsifier": {
            "command": "pytest -k demo_falsifier",
            "description": "demo falsifier",
        },
        "rollback_command": "git checkout -- src/demo.py",
        "rollback_verification_command": "git diff --exit-code src/demo.py",
        "memory_update_type": "append",
        "ledger_path": ".claude/commit_acceptors/demo.yaml",
        "report_path": "docs/reports/demo.md",
        "evidence": [],
    }
    for k, v in overrides.items():
        if v is None:
            base.pop(k, None)
        else:
            base[k] = v
    return base


def _write_acceptor(tmp_path: Path, name: str, body: dict[str, Any]) -> Path:
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    return p


def _file_loader_factory(files: dict[str, str]) -> Callable[[str], str | None]:
    def _load(rel: str) -> str | None:
        return files.get(rel)

    return _load


# ---------------------------------------------------------------------------
# 1-9 Schema
# ---------------------------------------------------------------------------


def test_01_required_fields_constant_matches_dataclass() -> None:
    rf = RequiredFields()
    assert rf.top_level == REQUIRED_TOP_LEVEL
    assert "id" in rf.top_level
    assert "promise" in rf.top_level
    assert "falsifier" in rf.top_level


def test_02_valid_acceptor_passes_schema(tmp_path: Path) -> None:
    p = _write_acceptor(tmp_path, "demo", _valid_acceptor())
    res = validate_acceptors(POLICY, [(p, _valid_acceptor())])
    assert res.ok, res.errors


def test_03_missing_required_field_errors(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body.pop("promise")
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("'promise'" in e for e in res.errors)


def test_04_invalid_status_errors(tmp_path: Path) -> None:
    body = _valid_acceptor(status="MAYBE")
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("status" in e for e in res.errors)


def test_05_invalid_claim_type_errors(tmp_path: Path) -> None:
    body = _valid_acceptor(claim_type="vibes")
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("claim_type" in e for e in res.errors)


def test_06_forbidden_schema_field_top_level_errors(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["forbidden_symbols"] = ["x"]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("forbidden_symbols" in e for e in res.errors)


def test_07_forbidden_schema_field_nested_errors(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["diff_scope"]["max_files_changed"] = 99
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("max_files_changed" in e for e in res.errors)


def test_08_generated_at_anywhere_errors(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["evidence"] = [{"path": "x", "sha256": "deadbeef", "generated_at": "now"}]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("generated_at" in e for e in res.errors)


def test_09_duplicate_id_errors(tmp_path: Path) -> None:
    a = _valid_acceptor()
    b = _valid_acceptor()
    pa = _write_acceptor(tmp_path, "a", a)
    pb = _write_acceptor(tmp_path, "b", b)
    res = validate_acceptors(POLICY, [(pa, a), (pb, b)])
    assert any("duplicate id" in e for e in res.errors)


# ---------------------------------------------------------------------------
# 10-16 AST forbidden imports
# ---------------------------------------------------------------------------


def test_10_clean_source_no_violations() -> None:
    src = "import os\nimport math\n"
    assert forbidden_imports(src, ["trading", "execution"]) == []


def test_11_direct_forbidden_import_caught() -> None:
    src = "import trading\n"
    out = forbidden_imports(src, ["trading"])
    assert out == ["trading"]


def test_12_dotted_forbidden_import_caught() -> None:
    src = "import trading.engine.core\n"
    out = forbidden_imports(src, ["trading"])
    assert out == ["trading.engine.core"]


def test_13_from_import_caught() -> None:
    src = "from execution.broker import Broker\n"
    out = forbidden_imports(src, ["execution"])
    assert out == ["execution.broker"]


def test_14_relative_import_two_directions() -> None:
    """Audit Holes 1 & 2: relative-import semantics in both directions.

    (a) ``from . import trading``  IS flagged — the alias name targets a
        forbidden module (Hole 1: bypass closed).
    (b) ``from .trading import x``  IS NOT flagged — ``.trading`` is a
        repo-local sibling submodule (Hole 2: false positive removed).
    (c) ``from . import sibling`` (non-forbidden alias) stays skipped.
    """
    # (a) Hole 1: bypass via `from . import trading` is now caught.
    caught = forbidden_imports("from . import trading\n", ["trading"])
    assert caught == ["trading"], caught

    # (b) Hole 2: `.trading` as the relative module is a local sibling,
    # NOT the forbidden absolute `trading` runtime module.
    not_caught = forbidden_imports("from .trading import helper\n", ["trading"])
    assert not_caught == [], not_caught

    # (c) Original behavior preserved: relative imports of non-forbidden
    # names stay clean.
    assert (
        forbidden_imports("from . import sibling\nfrom .helpers import fn\n", ["execution"]) == []
    )


def test_15_string_literal_not_inspected() -> None:
    src = 'X = "import trading"\n'
    assert forbidden_imports(src, ["trading"]) == []


def test_16_comment_not_inspected() -> None:
    src = "# import trading\nimport os\n"
    assert forbidden_imports(src, ["trading"]) == []


# ---------------------------------------------------------------------------
# 17-25 Diff binding
# ---------------------------------------------------------------------------


def test_17_code_change_with_acceptor_passes(tmp_path: Path) -> None:
    body = _valid_acceptor()
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["src/demo.py"],
        _file_loader_factory({"src/demo.py": "import os\n"}),
    )
    assert res.ok, res.errors


def test_18_code_change_without_acceptor_fails(tmp_path: Path) -> None:
    body = _valid_acceptor()
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["src/orphan.py"],
        _file_loader_factory({"src/orphan.py": "import os\n"}),
    )
    assert not res.ok
    assert any("code change without acceptor" in e for e in res.errors)


def test_19_governance_markdown_under_governance_path_ignored(tmp_path: Path) -> None:
    body = _valid_acceptor()
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        [".claude/notes.md"],
        _file_loader_factory({}),
    )
    assert res.ok, res.errors


def test_20_markdown_outside_governance_treated_as_code(tmp_path: Path) -> None:
    body = _valid_acceptor()
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["random.md"],
        _file_loader_factory({}),
    )
    assert not res.ok


def test_21_forbidden_path_claim_fails(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["diff_scope"]["changed_files"] = [{"path": "trading/engine.py"}]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["trading/engine.py"],
        _file_loader_factory({"trading/engine.py": "import os\n"}),
    )
    assert not res.ok
    assert any("forbidden_path" in e for e in res.errors)


def test_22_per_claim_type_cap_enforced(tmp_path: Path) -> None:
    body = _valid_acceptor(claim_type="performance")
    files = [{"path": f"src/f{i}.py"} for i in range(11)]
    body["diff_scope"]["changed_files"] = files
    p = _write_acceptor(tmp_path, "demo", body)
    changed = [f["path"] for f in files]
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        changed,
        _file_loader_factory({c: "import os\n" for c in changed}),
    )
    assert any("exceeds cap" in e for e in res.errors)


def test_23_draft_subject_to_cap(tmp_path: Path) -> None:
    body = _valid_acceptor(status="DRAFT", claim_type="performance")
    files = [{"path": f"src/f{i}.py"} for i in range(11)]
    body["diff_scope"]["changed_files"] = files
    p = _write_acceptor(tmp_path, "demo", body)
    changed = [f["path"] for f in files]
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        changed,
        _file_loader_factory({c: "import os\n" for c in changed}),
    )
    assert any("exceeds cap" in e for e in res.errors)


def test_24_unbound_python_skipped_for_ast_when_loader_none(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["diff_scope"]["changed_files"] = [{"path": "src/demo.py"}]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["src/demo.py"],
        _file_loader_factory({}),
    )
    # Loader returns None - file deleted in HEAD - schema OK, no AST violation.
    assert res.ok, res.errors


def test_25_forbidden_import_in_changed_py_file_fails(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["diff_scope"]["changed_files"] = [{"path": "src/demo.py"}]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["src/demo.py"],
        _file_loader_factory({"src/demo.py": "import trading.engine\n"}),
    )
    assert not res.ok
    assert any("forbidden import" in e for e in res.errors)


# ---------------------------------------------------------------------------
# 26-30 Evidence hashing
# ---------------------------------------------------------------------------


def test_26_compute_artifact_hashes_present(tmp_path: Path) -> None:
    art = tmp_path / "tmp" / "demo.log"
    art.parent.mkdir()
    art.write_bytes(b"hello")
    body = _valid_acceptor(signal_artifact="tmp/demo.log")
    h = compute_artifact_hashes(body, tmp_path)
    expected = hashlib.sha256(b"hello").hexdigest()
    assert h["tmp/demo.log"] == expected


def test_27_compute_artifact_hashes_missing(tmp_path: Path) -> None:
    body = _valid_acceptor(signal_artifact="tmp/missing.log")
    h = compute_artifact_hashes(body, tmp_path)
    assert h["tmp/missing.log"] == "MISSING"


def test_28_evidence_explicit_path_hashed(tmp_path: Path) -> None:
    art = tmp_path / "ev.txt"
    art.write_bytes(b"E")
    body = _valid_acceptor(evidence=[{"path": "ev.txt"}])
    h = compute_artifact_hashes(body, tmp_path)
    assert h["ev.txt"] == hashlib.sha256(b"E").hexdigest()


def test_29_verified_with_missing_evidence_errors(tmp_path: Path) -> None:
    body = _valid_acceptor(status="VERIFIED", signal_artifact="tmp/missing.log")
    p = _write_acceptor(tmp_path, "demo", body)
    # Use main() path indirectly: spin up env and run main with a tmp policy
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    acc_dir = tmp_path / "accs"
    acc_dir.mkdir()
    (acc_dir / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "tmp" / "out.json"
    rc = main(
        [
            str(acc_dir),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(out),
            "--template",
            "",
        ]
    )
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert any("evidence missing" in e for e in payload["errors"])


def test_30_active_with_missing_evidence_warns_only(tmp_path: Path) -> None:
    body = _valid_acceptor(status="ACTIVE", signal_artifact="tmp/missing.log")
    p = _write_acceptor(tmp_path, "demo", body)
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    acc_dir = tmp_path / "accs"
    acc_dir.mkdir()
    (acc_dir / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "tmp" / "out.json"
    rc = main(
        [
            str(acc_dir),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(out),
            "--template",
            "",
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert any("evidence missing" in w for w in payload["warnings"])


# ---------------------------------------------------------------------------
# 31-37 CLI / status / id consistency / falsifier
# ---------------------------------------------------------------------------


def test_31_template_id_must_be_template(tmp_path: Path) -> None:
    body = _valid_acceptor(id="not-template", status="DRAFT")
    p = tmp_path / "commit_acceptor_template.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("template id" in e for e in res.errors)


def test_32_filename_id_mismatch_in_acceptors_dir(tmp_path: Path) -> None:
    body = _valid_acceptor(id="wrong")
    sub = tmp_path / "commit_acceptors"
    sub.mkdir()
    p = sub / "expected.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("must match filename stem" in e for e in res.errors)


def test_33_rejected_requires_falsifier_description(tmp_path: Path) -> None:
    body = _valid_acceptor(
        status="REJECTED",
        falsifier={"command": "x", "description": ""},
    )
    sub = tmp_path / "commit_acceptors"
    sub.mkdir()
    p = sub / "demo.yaml"
    body["id"] = "demo"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("REJECTED status" in e for e in res.errors)


def test_34_invalid_memory_update_type(tmp_path: Path) -> None:
    body = _valid_acceptor(memory_update_type="forever")
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("memory_update_type" in e for e in res.errors)


def test_35_falsifier_missing_field(tmp_path: Path) -> None:
    body = _valid_acceptor(falsifier={"command": "x"})
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("falsifier missing" in e for e in res.errors)


def test_36_diff_scope_missing(tmp_path: Path) -> None:
    body = _valid_acceptor(diff_scope=None)
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("diff_scope" in e for e in res.errors)


def test_37_changed_files_must_be_nonempty_list(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["diff_scope"]["changed_files"] = []
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert any("non-empty list" in e for e in res.errors)


# ---------------------------------------------------------------------------
# 38-41 JSON determinism / idempotence / CLI exit codes
# ---------------------------------------------------------------------------


def test_38_json_summary_has_no_generated_at(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["id"] = "demo"
    sub = tmp_path / "commit_acceptors"
    sub.mkdir()
    (sub / "demo.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    out = tmp_path / "tmp" / "out.json"
    rc = main(
        [
            str(sub),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(out),
            "--template",
            "",
        ]
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "generated_at" not in text


def test_39_cli_returns_2_on_missing_acceptors_dir(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    rc = main(
        [
            str(tmp_path / "does_not_exist"),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(tmp_path / "out.json"),
            "--template",
            "",
        ]
    )
    assert rc == 2


def test_40_cli_returns_2_on_malformed_yaml(tmp_path: Path) -> None:
    sub = tmp_path / "commit_acceptors"
    sub.mkdir()
    (sub / "broken.yaml").write_text("key: : :\n  - bad", encoding="utf-8")
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    rc = main(
        [
            str(sub),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(tmp_path / "out.json"),
            "--template",
            "",
        ]
    )
    assert rc == 2


def test_41_validator_does_not_mutate_acceptor_yaml(tmp_path: Path) -> None:
    body = _valid_acceptor()
    body["id"] = "demo"
    sub = tmp_path / "commit_acceptors"
    sub.mkdir()
    p = sub / "demo.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    out = tmp_path / "tmp" / "out.json"
    main(
        [
            str(sub),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(out),
            "--template",
            "",
        ]
    )
    after = hashlib.sha256(p.read_bytes()).hexdigest()
    assert before == after


# ---------------------------------------------------------------------------
# Diff fetcher exercised via subprocess monkeypatch (smoke; not numbered)
# ---------------------------------------------------------------------------


def test_diff_fetcher_subprocess_monkeypatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Smoke test that the subprocess-based git-diff path is exercised."""
    from tools.commit_acceptor import validate_commit_acceptor as mod

    class _FakeProc:
        returncode = 0
        stdout = "src/demo.py\n"

    def _fake_run(*_args: Any, **_kwargs: Any) -> _FakeProc:
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    files = mod._git_diff_files("origin/main", "HEAD")
    assert files == ["src/demo.py"]


def test_validation_result_dataclass_basic() -> None:
    r = ValidationResult()
    assert r.ok is True
    r.errors.append("e")
    assert r.ok is False
    r2 = ValidationResult(warnings=["w"])
    r.merge(r2)
    assert "w" in r.warnings


def test_subprocess_module_imported() -> None:
    """Sanity probe so import of subprocess is not flagged unused."""
    assert hasattr(subprocess, "run")


# ---------------------------------------------------------------------------
# Audit holes 3, 4, 5: path traversal, empty/whitespace, null promise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "../etc/passwd",
        "geosync/../../escape",
        "/abs/path",
        "path\\windows",
        "..",
        "a/../b",
    ],
)
def test_path_traversal_in_changed_files_rejected(tmp_path: Path, bad_path: str) -> None:
    """Audit Hole 3: changed_files[*].path must reject traversal/absolute/backslash."""
    body = _valid_acceptor()
    body["diff_scope"]["changed_files"] = [{"path": bad_path}]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("unsafe" in e and "changed_files" in e for e in res.errors), res.errors


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape/",
        "/abs/forbid",
        "back\\slash/",
    ],
)
def test_path_traversal_in_forbidden_paths_rejected(tmp_path: Path, bad_path: str) -> None:
    """Audit Hole 3 (symmetric): forbidden_paths must also reject traversal."""
    body = _valid_acceptor()
    body["diff_scope"]["forbidden_paths"] = [bad_path]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("unsafe" in e and "forbidden_paths" in e for e in res.errors), res.errors


def test_empty_id_rejected(tmp_path: Path) -> None:
    """Audit Hole 4: id == "" must be rejected."""
    body = _valid_acceptor(id="")
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("id must be a non-empty string" in e for e in res.errors), res.errors


def test_whitespace_id_rejected(tmp_path: Path) -> None:
    """Audit Hole 4: id of only whitespace must be rejected."""
    body = _valid_acceptor(id="   ")
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("id must be a non-empty string" in e for e in res.errors), res.errors


def test_empty_promise_summary_rejected(tmp_path: Path) -> None:
    """Audit Hole 4: promise as empty string must be rejected."""
    body = _valid_acceptor(promise="")
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("promise" in e and "non-empty" in e for e in res.errors), res.errors


def test_whitespace_promise_summary_rejected(tmp_path: Path) -> None:
    """Audit Hole 4: promise as whitespace-only string must be rejected."""
    body = _valid_acceptor(promise="   \t\n")
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("promise" in e and "non-empty" in e for e in res.errors), res.errors


def test_promise_dict_with_empty_summary_rejected(tmp_path: Path) -> None:
    """Audit Hole 4 (dict shape): promise.summary empty/whitespace rejected."""
    body = _valid_acceptor(promise={"summary": "   "})
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("promise.summary" in e for e in res.errors), res.errors


def test_null_promise_block_rejected(tmp_path: Path) -> None:
    """Audit Hole 5: promise: null (None) must be rejected with INVALID_PROMISE_BLOCK."""
    body = _valid_acceptor(promise=None)
    # _valid_acceptor pops keys with value None, so set explicitly.
    body["promise"] = None
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("INVALID_PROMISE_BLOCK" in e for e in res.errors), res.errors


def test_promise_wrong_type_rejected(tmp_path: Path) -> None:
    """Audit Hole 5 (extension): promise as list/int rejected with INVALID_PROMISE_BLOCK."""
    body = _valid_acceptor()
    body["promise"] = ["not", "a", "string"]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_acceptors(POLICY, [(p, body)])
    assert not res.ok
    assert any("INVALID_PROMISE_BLOCK" in e for e in res.errors), res.errors


# ---------------------------------------------------------------------------
# Dep-manifest exemption (added to unblock Dependabot bumps that touch only
# package.json / package-lock.json / yarn.lock / pnpm-lock.yaml).
# ---------------------------------------------------------------------------


def test_dep_manifest_package_json_exempt_without_acceptor(tmp_path: Path) -> None:
    """Lone package.json bump must NOT require an acceptor."""
    body = _valid_acceptor()
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["apps/web/package.json", "apps/web/package-lock.json"],
        _file_loader_factory({}),
    )
    assert res.ok, res.errors


def test_dep_manifest_yarn_lock_exempt_without_acceptor(tmp_path: Path) -> None:
    body = _valid_acceptor()
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["ui/dashboard/yarn.lock", "ui/dashboard/pnpm-lock.yaml"],
        _file_loader_factory({}),
    )
    assert res.ok, res.errors


def test_dep_manifest_exemption_does_not_apply_to_workflow_yml(tmp_path: Path) -> None:
    """Workflow YAML bumps still require an acceptor (intentionally NOT exempt)."""
    body = _valid_acceptor()
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        [".github/workflows/pr-gate.yml"],
        _file_loader_factory({".github/workflows/pr-gate.yml": "name: x\n"}),
    )
    assert not res.ok, "workflow YAML must NOT be exempt from acceptor binding"
    assert any("code change without acceptor" in e for e in res.errors)


def test_dep_manifest_exemption_does_not_apply_to_arbitrary_json(tmp_path: Path) -> None:
    """A JSON file that is NOT a known dep-manifest must still bind."""
    body = _valid_acceptor()
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["src/config/app_settings.json"],
        _file_loader_factory({"src/config/app_settings.json": "{}\n"}),
    )
    assert not res.ok
    assert any("code change without acceptor" in e for e in res.errors)


def test_dep_manifest_mixed_change_partial_binding(tmp_path: Path) -> None:
    """Mixed bump: dep-manifest exempt; sibling .py code still bound to acceptor."""
    body = _valid_acceptor()
    body["diff_scope"]["changed_files"] = [{"path": "src/demo.py"}]
    p = _write_acceptor(tmp_path, "demo", body)
    res = validate_diff_binding(
        POLICY,
        [(p, body)],
        ["apps/web/package.json", "src/demo.py"],
        _file_loader_factory({"src/demo.py": "import os\n"}),
    )
    assert res.ok, res.errors


def test_cli_acceptor_id_scopes_validation_warnings(tmp_path: Path) -> None:
    """--acceptor-id validates one acceptor without unrelated evidence warnings."""

    sub = tmp_path / "commit_acceptors"
    sub.mkdir()
    selected = _valid_acceptor(id="selected")
    selected["ledger_path"] = ".claude/commit_acceptors/selected.yaml"
    selected["signal_artifact"] = "README.md"
    selected["evidence"] = []
    unrelated = _valid_acceptor(id="unrelated")
    unrelated["ledger_path"] = ".claude/commit_acceptors/unrelated.yaml"
    unrelated["signal_artifact"] = "tmp/missing-unrelated.log"
    unrelated["evidence"] = [{"path": "tmp/missing-unrelated.log"}]
    (sub / "selected.yaml").write_text(yaml.safe_dump(selected), encoding="utf-8")
    (sub / "unrelated.yaml").write_text(yaml.safe_dump(unrelated), encoding="utf-8")
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    out = tmp_path / "summary.json"

    rc = main(
        [
            str(sub),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(out),
            "--template",
            "",
            "--acceptor-id",
            "selected",
        ]
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["ok"] is True
    assert payload["warnings"] == []
    assert [acceptor["id"] for acceptor in payload["acceptors"]] == ["selected"]


def test_cli_acceptor_id_returns_2_for_unknown_id(tmp_path: Path) -> None:
    sub = tmp_path / "commit_acceptors"
    sub.mkdir()
    body = _valid_acceptor(id="selected")
    body["ledger_path"] = ".claude/commit_acceptors/selected.yaml"
    (sub / "selected.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")

    rc = main(
        [
            str(sub),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(tmp_path / "summary.json"),
            "--template",
            "",
            "--acceptor-id",
            "missing",
        ]
    )

    assert rc == 2


def test_cli_acceptor_id_can_select_multiple_acceptors(tmp_path: Path) -> None:
    sub = tmp_path / "commit_acceptors"
    sub.mkdir()
    for acceptor_id in ("first", "second", "third"):
        body = _valid_acceptor(id=acceptor_id)
        body["ledger_path"] = f".claude/commit_acceptors/{acceptor_id}.yaml"
        body["signal_artifact"] = "README.md"
        body["evidence"] = []
        (sub / f"{acceptor_id}.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    out = tmp_path / "summary.json"

    rc = main(
        [
            str(sub),
            "--policy",
            str(policy_path),
            "--summary-out",
            str(out),
            "--template",
            "",
            "--acceptor-id",
            "first",
            "--acceptor-id",
            "third",
        ]
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["warnings"] == []
    assert [acceptor["id"] for acceptor in payload["acceptors"]] == ["first", "third"]
