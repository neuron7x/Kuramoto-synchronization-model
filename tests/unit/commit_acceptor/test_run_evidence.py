# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the commit-acceptor evidence runner.

Tests are aware of the falsifier-mutation probes documented in the
PR body. Each docstring lists which probe(s) the test catches.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest
import yaml

from tools.commit_acceptor.run_evidence import (
    _select_acceptors,
    main,
    run_acceptor,
    update_acceptor_yaml,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _make_acceptor(
    *,
    aid: str = "test-acceptor",
    status: str = "ACTIVE",
    measurement_command: str = "echo signal",
    falsifier_command: str = "echo falsifier",
    signal_artifact: str = "tmp/signal.log",
    falsifier_artifact: str = "tmp/falsifier.log",
    evidence_paths: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": aid,
        "status": status,
        "claim_type": "governance",
        "promise": "test acceptor",
        "diff_scope": {
            "changed_files": [{"path": "tools/commit_acceptor/run_evidence.py"}],
            "forbidden_paths": ["trading/"],
        },
        "required_python_symbols": ["run_acceptor"],
        "expected_signal": "ok",
        "measurement_command": measurement_command,
        "signal_artifact": signal_artifact,
        "falsifier": {
            "command": falsifier_command,
            "description": "probe description",
            "falsifier_artifact": falsifier_artifact,
        },
        "rollback_command": "git checkout --",
        "rollback_verification_command": "git diff --exit-code",
        "memory_update_type": "append",
        "ledger_path": ".claude/commit_acceptors/test-acceptor.yaml",
        "report_path": "docs/reports/test.md",
        "evidence": [{"path": p} for p in (evidence_paths or [])],
    }


def _fake_runner(
    signal_exit: int = 0,
    falsifier_exit: int = 0,
    signal_out: str = "OK",
    falsifier_out: str = "OK",
) -> Callable[[str, float], CompletedProcess[str]]:
    """Return a runner callable that maps known commands to scripted exits."""

    def _run(cmd: str, timeout_s: float) -> CompletedProcess[str]:
        if "signal" in cmd:
            return CompletedProcess(args=cmd, returncode=signal_exit, stdout=signal_out, stderr="")
        if "falsifier" in cmd:
            return CompletedProcess(
                args=cmd, returncode=falsifier_exit, stdout=falsifier_out, stderr=""
            )
        return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    return _run


# ---------------------------------------------------------------------------
# Test 1: ACTIVE acceptor with passing commands -> PASS verdict.
# Catches mutation probe #3 (always return PASS).
# ---------------------------------------------------------------------------


def test_active_passing_commands_yields_pass(tmp_path: Path) -> None:
    """ACTIVE acceptor + zero exits + artifacts present -> verdict PASS.

    Probe #3 mutation (always return PASS regardless of exit codes) does
    NOT differ from this test on this single input — the negative tests
    below kill that mutant.
    """
    acc = _make_acceptor()
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    assert result.verdict == "PASS"
    assert result.success is True
    assert result.signal_exit_code == 0
    assert result.falsifier_exit_code == 0
    assert result.signal_artifact_sha256 is not None
    assert len(result.signal_artifact_sha256) == 64


# ---------------------------------------------------------------------------
# Test 2: failing measurement_command -> SIGNAL_FAILED.
# Catches probe #3 (always-PASS mutant).
# ---------------------------------------------------------------------------


def test_failing_measurement_command_yields_signal_failed(tmp_path: Path) -> None:
    """signal_exit_code != 0 -> SIGNAL_FAILED. Kills 'always-PASS' mutant."""
    acc = _make_acceptor()
    result = run_acceptor(acc, tmp_path, runner=_fake_runner(signal_exit=1))
    assert result.verdict == "SIGNAL_FAILED"
    assert result.success is False


# ---------------------------------------------------------------------------
# Test 3: failing falsifier -> SIGNAL_FAILED.
# Catches probe #3 (always-PASS mutant).
# ---------------------------------------------------------------------------


def test_failing_falsifier_yields_signal_failed(tmp_path: Path) -> None:
    """falsifier_exit_code != 0 -> SIGNAL_FAILED (green-state broken)."""
    acc = _make_acceptor()
    result = run_acceptor(acc, tmp_path, runner=_fake_runner(falsifier_exit=2))
    assert result.verdict == "SIGNAL_FAILED"
    assert result.success is False


# ---------------------------------------------------------------------------
# Test 4: missing declared evidence artifact -> ARTIFACTS_MISSING.
# Catches probe #4 (skip artifact existence check).
# ---------------------------------------------------------------------------


def test_missing_evidence_artifact_yields_artifacts_missing(tmp_path: Path) -> None:
    """Declared evidence artifact that doesn't exist -> ARTIFACTS_MISSING.

    Kills probe #4 mutant (skip artifact existence check, which would
    pass-through with verdict PASS).
    """
    acc = _make_acceptor(evidence_paths=["tmp/does_not_exist.bin"])
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    assert result.verdict == "ARTIFACTS_MISSING"
    assert result.success is False


# ---------------------------------------------------------------------------
# Test 5: hash determinism (run twice -> identical hashes).
# Catches probe #2 indirectly (string equality vs sha256).
# ---------------------------------------------------------------------------


def test_hash_determinism(tmp_path: Path) -> None:
    """Two runs with identical inputs produce identical artifact hashes."""
    acc = _make_acceptor()
    r1 = run_acceptor(acc, tmp_path, runner=_fake_runner(signal_out="abc", falsifier_out="def"))
    r2 = run_acceptor(acc, tmp_path, runner=_fake_runner(signal_out="abc", falsifier_out="def"))
    assert r1.signal_artifact_sha256 == r2.signal_artifact_sha256
    assert r1.falsifier_artifact_sha256 == r2.falsifier_artifact_sha256
    assert r1.signal_artifact_sha256 is not None
    # 64-char lowercase hex.
    assert len(r1.signal_artifact_sha256) == 64
    assert all(c in "0123456789abcdef" for c in r1.signal_artifact_sha256)


# ---------------------------------------------------------------------------
# Test 6: evidence_sha256 list is sorted alphabetically by artifact path.
# Catches probe #6 (strip the sort).
# ---------------------------------------------------------------------------


def test_evidence_sha256_sorted_alphabetically(tmp_path: Path) -> None:
    """The evidence_sha256 list written to YAML must be sorted by path.

    Kills probe #6 mutant (strip sort) — without sort, the list order
    depends on dict insertion order which is not declarative.
    """
    # Create three pre-existing evidence artifacts with non-alphabetical names.
    paths_in_order = ["tmp/zzz.txt", "tmp/aaa.txt", "tmp/mmm.txt"]
    for rel in paths_in_order:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"contents-of-{rel}", encoding="utf-8")

    acc = _make_acceptor(evidence_paths=paths_in_order)
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    assert result.verdict == "PASS"

    # Write to a temp acceptor file and re-load.
    acc_path = tmp_path / "acc.yaml"
    acc_path.write_text(yaml.safe_dump(acc, sort_keys=False), encoding="utf-8")
    update_acceptor_yaml(acc_path, result, promote_to_verified=False)
    reloaded = yaml.safe_load(acc_path.read_text(encoding="utf-8"))
    sha_list = reloaded["evidence_sha256"]
    paths_written = [e["path"] for e in sha_list]
    assert paths_written == sorted(paths_written)


# ---------------------------------------------------------------------------
# Test 7: --promote with PASS verdict updates status to VERIFIED.
# Catches probe #1 (skip --promote gate would still pass; this test asserts
# the positive direction).
# ---------------------------------------------------------------------------


def test_promote_with_pass_sets_status_verified(tmp_path: Path) -> None:
    """update_acceptor_yaml(promote=True) on PASS -> status=VERIFIED."""
    acc = _make_acceptor()
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    assert result.success is True
    acc_path = tmp_path / "acc.yaml"
    acc_path.write_text(yaml.safe_dump(acc, sort_keys=False), encoding="utf-8")
    update_acceptor_yaml(acc_path, result, promote_to_verified=True)
    reloaded = yaml.safe_load(acc_path.read_text(encoding="utf-8"))
    assert reloaded["status"] == "VERIFIED"


# ---------------------------------------------------------------------------
# Test 8: --promote with SIGNAL_FAILED does NOT promote.
# Kills probe #1 (skip the --promote-only gate).
# ---------------------------------------------------------------------------


def test_promote_with_signal_failed_does_not_promote(tmp_path: Path) -> None:
    """promote=True on non-PASS must NOT set status=VERIFIED.

    Kills probe #1 (drop the success guard around promotion).
    """
    acc = _make_acceptor()
    result = run_acceptor(acc, tmp_path, runner=_fake_runner(signal_exit=3))
    assert result.success is False
    acc_path = tmp_path / "acc.yaml"
    acc_path.write_text(yaml.safe_dump(acc, sort_keys=False), encoding="utf-8")
    update_acceptor_yaml(acc_path, result, promote_to_verified=True)
    reloaded = yaml.safe_load(acc_path.read_text(encoding="utf-8"))
    assert reloaded["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# Test 9: without --promote, status unchanged regardless of verdict.
# ---------------------------------------------------------------------------


def test_no_promote_preserves_status(tmp_path: Path) -> None:
    """promote_to_verified=False keeps status untouched."""
    acc = _make_acceptor(status="ACTIVE")
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    acc_path = tmp_path / "acc.yaml"
    acc_path.write_text(yaml.safe_dump(acc, sort_keys=False), encoding="utf-8")
    update_acceptor_yaml(acc_path, result, promote_to_verified=False)
    reloaded = yaml.safe_load(acc_path.read_text(encoding="utf-8"))
    assert reloaded["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# Test 10: DRAFT acceptors are SKIPPED. Kills probe #5 (run DRAFT).
# ---------------------------------------------------------------------------


def test_draft_acceptors_skipped(tmp_path: Path) -> None:
    """DRAFT acceptors must be skipped by _select_acceptors. Kills probe #5."""
    acc_dir = tmp_path / "acc"
    acc_dir.mkdir()
    (acc_dir / "draft.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="draft", status="DRAFT"), sort_keys=False),
        encoding="utf-8",
    )
    selected = _select_acceptors(acc_dir, acceptor_id=None, re_verify=False)
    assert selected == []


# ---------------------------------------------------------------------------
# Test 11: REJECTED acceptors are SKIPPED.
# ---------------------------------------------------------------------------


def test_rejected_acceptors_skipped(tmp_path: Path) -> None:
    """REJECTED acceptors must be skipped."""
    acc_dir = tmp_path / "acc"
    acc_dir.mkdir()
    (acc_dir / "rej.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="rej", status="REJECTED"), sort_keys=False),
        encoding="utf-8",
    )
    selected = _select_acceptors(acc_dir, acceptor_id=None, re_verify=False)
    assert selected == []


# ---------------------------------------------------------------------------
# Test 12: VERIFIED skipped unless --re-verify.
# ---------------------------------------------------------------------------


def test_verified_skipped_unless_reverify(tmp_path: Path) -> None:
    """VERIFIED acceptors only run when --re-verify flag is on."""
    acc_dir = tmp_path / "acc"
    acc_dir.mkdir()
    (acc_dir / "ver.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="ver", status="VERIFIED"), sort_keys=False),
        encoding="utf-8",
    )
    assert _select_acceptors(acc_dir, acceptor_id=None, re_verify=False) == []
    selected = _select_acceptors(acc_dir, acceptor_id=None, re_verify=True)
    assert len(selected) == 1


# ---------------------------------------------------------------------------
# Test 13: --acceptor-id selects only one acceptor by id.
# ---------------------------------------------------------------------------


def test_acceptor_id_filters_to_one(tmp_path: Path) -> None:
    """--acceptor-id selects a single acceptor by exact id match."""
    acc_dir = tmp_path / "acc"
    acc_dir.mkdir()
    (acc_dir / "alpha.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="alpha"), sort_keys=False),
        encoding="utf-8",
    )
    (acc_dir / "beta.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="beta"), sort_keys=False),
        encoding="utf-8",
    )
    selected = _select_acceptors(acc_dir, acceptor_id="alpha", re_verify=False)
    assert [acc.get("id") for _, acc in selected] == ["alpha"]


# ---------------------------------------------------------------------------
# Test 14: --all runs every ACTIVE acceptor.
# ---------------------------------------------------------------------------


def test_all_runs_every_active(tmp_path: Path) -> None:
    """No --acceptor-id: every ACTIVE acceptor in the dir is selected."""
    acc_dir = tmp_path / "acc"
    acc_dir.mkdir()
    (acc_dir / "alpha.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="alpha"), sort_keys=False),
        encoding="utf-8",
    )
    (acc_dir / "beta.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="beta"), sort_keys=False),
        encoding="utf-8",
    )
    (acc_dir / "draft.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="draft", status="DRAFT"), sort_keys=False),
        encoding="utf-8",
    )
    selected = _select_acceptors(acc_dir, acceptor_id=None, re_verify=False)
    ids = [acc.get("id") for _, acc in selected]
    assert sorted(str(i) for i in ids) == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# Test 15: JSON summary has no `generated_at`, sorted keys.
# ---------------------------------------------------------------------------


def test_summary_has_no_generated_at_and_is_sorted(tmp_path: Path) -> None:
    """Summary JSON must be deterministic: sorted keys, no timestamps."""
    acc_dir = tmp_path / ".claude" / "commit_acceptors"
    acc_dir.mkdir(parents=True)
    (tmp_path / ".git").mkdir()  # mark as repo root for _resolve_repo_root fallback
    (acc_dir / "alpha.yaml").write_text(
        yaml.safe_dump(_make_acceptor(aid="alpha"), sort_keys=False),
        encoding="utf-8",
    )
    summary_out = tmp_path / "summary.json"
    rc = main(
        [
            "--all",
            "--acceptors-dir",
            str(acc_dir),
            "--summary-out",
            str(summary_out),
            "--repo-root",
            str(tmp_path),
        ]
    )
    # rc may be 0 or 1 depending on whether the actual subprocess "echo signal"
    # works on this system, but the file MUST be deterministic regardless.
    assert summary_out.is_file()
    payload = json.loads(summary_out.read_text(encoding="utf-8"))
    assert "generated_at" not in payload
    # Top-level keys are sorted.
    assert list(payload.keys()) == sorted(payload.keys())
    # The exit code follows verdict (0 or 1, never 2 here).
    assert rc in (0, 1)


# ---------------------------------------------------------------------------
# Test 16: timeout enforces -- mock a sleep command.
# ---------------------------------------------------------------------------


def test_timeout_enforces_signal_failed(tmp_path: Path) -> None:
    """A runner that raises TimeoutExpired -> SIGNAL_FAILED with timeout msg."""
    acc = _make_acceptor()

    def _slow(cmd: str, timeout_s: float) -> CompletedProcess[str]:
        if "signal" in cmd:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_s)
        return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    result = run_acceptor(acc, tmp_path, timeout_s=10.0, runner=_slow)
    assert result.verdict == "SIGNAL_FAILED"
    assert any("timeout" in m.lower() for m in result.messages)


# ---------------------------------------------------------------------------
# Test 17: --timeout-s 1 rejected (out of [10, 3600]).
# ---------------------------------------------------------------------------


def test_timeout_too_low_rejected() -> None:
    """run_acceptor with timeout < MIN must raise ValueError."""
    acc = _make_acceptor()
    with pytest.raises(ValueError):
        run_acceptor(acc, Path("/tmp"), timeout_s=1.0)


# ---------------------------------------------------------------------------
# Test 18: --timeout-s 99999 rejected (out of range).
# ---------------------------------------------------------------------------


def test_timeout_too_high_rejected() -> None:
    """run_acceptor with timeout > MAX must raise ValueError."""
    acc = _make_acceptor()
    with pytest.raises(ValueError):
        run_acceptor(acc, Path("/tmp"), timeout_s=99999.0)


# ---------------------------------------------------------------------------
# Test 19: update_acceptor_yaml preserves all top-level keys.
# ---------------------------------------------------------------------------


def test_update_yaml_preserves_top_level_keys(tmp_path: Path) -> None:
    """Round-trip: every top-level key present before is present after."""
    acc = _make_acceptor()
    acc_path = tmp_path / "acc.yaml"
    acc_path.write_text(yaml.safe_dump(acc, sort_keys=False), encoding="utf-8")
    keys_before = set(yaml.safe_load(acc_path.read_text(encoding="utf-8")).keys())
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    update_acceptor_yaml(acc_path, result, promote_to_verified=False)
    keys_after = set(yaml.safe_load(acc_path.read_text(encoding="utf-8")).keys())
    # All original keys preserved; one new key (evidence_sha256) added.
    assert keys_before <= keys_after
    assert "evidence_sha256" in keys_after


# ---------------------------------------------------------------------------
# Test 20: idempotence — running twice with identical successful inputs
# produces identical evidence_sha256 list AND identical YAML bytes.
# ---------------------------------------------------------------------------


def test_idempotence_yaml_byte_for_byte(tmp_path: Path) -> None:
    """Two runs with identical inputs produce byte-identical acceptor YAML."""
    acc = _make_acceptor()
    acc_path = tmp_path / "acc.yaml"
    acc_path.write_text(yaml.safe_dump(acc, sort_keys=False), encoding="utf-8")

    r1 = run_acceptor(acc, tmp_path, runner=_fake_runner(signal_out="X", falsifier_out="Y"))
    update_acceptor_yaml(acc_path, r1, promote_to_verified=True)
    bytes1 = acc_path.read_bytes()

    r2 = run_acceptor(acc, tmp_path, runner=_fake_runner(signal_out="X", falsifier_out="Y"))
    update_acceptor_yaml(acc_path, r2, promote_to_verified=True)
    bytes2 = acc_path.read_bytes()

    assert r1.evidence_artifact_sha256 == r2.evidence_artifact_sha256
    assert r1.signal_artifact_sha256 == r2.signal_artifact_sha256
    assert bytes1 == bytes2


# ---------------------------------------------------------------------------
# Test 21: run_acceptor accepts a custom runner callable (DI).
# ---------------------------------------------------------------------------


def test_runner_dependency_injection(tmp_path: Path) -> None:
    """run_acceptor must accept a custom runner callable for DI in tests."""
    calls: list[str] = []

    def _spy(cmd: str, timeout_s: float) -> CompletedProcess[str]:
        calls.append(cmd)
        return CompletedProcess(args=cmd, returncode=0, stdout="spy", stderr="")

    acc = _make_acceptor()
    result = run_acceptor(acc, tmp_path, runner=_spy)
    assert result.verdict == "PASS"
    # Both measurement and falsifier commands were dispatched through the spy.
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Test 22: signal_artifact_sha256 is a 64-char lowercase hex string.
# Kills probe #2 (substitute equality for full sha match).
# ---------------------------------------------------------------------------


def test_signal_hash_is_64char_lowercase_hex(tmp_path: Path) -> None:
    """sha256 hex must always be 64 lowercase hex chars."""
    acc = _make_acceptor()
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    assert result.signal_artifact_sha256 is not None
    assert len(result.signal_artifact_sha256) == 64
    assert result.signal_artifact_sha256 == result.signal_artifact_sha256.lower()
    assert all(c in "0123456789abcdef" for c in result.signal_artifact_sha256)


# ---------------------------------------------------------------------------
# Test 23: EvidenceResult.to_summary has no `generated_at` and sorts evidence keys.
# ---------------------------------------------------------------------------


def test_evidence_result_summary_sorted_no_timestamp(tmp_path: Path) -> None:
    """to_summary() output has sorted evidence dict and no timestamp field."""
    paths = ["tmp/z.txt", "tmp/a.txt"]
    for rel in paths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    acc = _make_acceptor(evidence_paths=paths)
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    summary = result.to_summary()
    assert "generated_at" not in summary
    keys = list(summary["evidence_artifact_sha256"].keys())
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Test 24: update_acceptor_yaml is NON-DESTRUCTIVE -- comment headers and the
# literal-block command scalars survive a promote round-trip verbatim. Locks in
# the surgical writer (the old yaml.dump round-trip stripped comments and could
# reflow `|-` command scalars, corrupting the very commands under test).
# ---------------------------------------------------------------------------


def test_update_yaml_preserves_comments_and_command_scalars(tmp_path: Path) -> None:
    """promote round-trip must not strip comments or reflow `|-` commands."""
    acc_text = (
        "# integrity gate: do NOT delete this header comment.\n"
        "# second comment line.\n"
        "id: preserve-probe\n"
        "status: ACTIVE\n"
        "claim_type: governance\n"
        "promise: keep me\n"
        "diff_scope:\n"
        "  changed_files:\n"
        "    - path: tools/commit_acceptor/run_evidence.py\n"
        "  forbidden_paths:\n"
        "    - trading/\n"
        "required_python_symbols:\n"
        "  - run_acceptor\n"
        "expected_signal: ok\n"
        "measurement_command: echo signal\n"
        "signal_artifact: tmp/signal.log\n"
        "falsifier:\n"
        "  command: |-\n"
        '    bash -c \'python -c "\n'
        "    import sys\n"
        "    falsifier_ok = True\n"
        "    sys.exit(0 if falsifier_ok else 1)\n"
        "    \"'\n"
        "  description: probe\n"
        "  falsifier_artifact: tmp/falsifier.log\n"
        "rollback_command: git checkout --\n"
        "rollback_verification_command: git diff --exit-code\n"
        "memory_update_type: append\n"
        "ledger_path: .claude/commit_acceptors/preserve-probe.yaml\n"
        "report_path: docs/reports/test.md\n"
    )
    acc_path = tmp_path / "preserve.yaml"
    acc_path.write_text(acc_text, encoding="utf-8")

    acc = yaml.safe_load(acc_text)
    original_command = acc["falsifier"]["command"]
    result = run_acceptor(acc, tmp_path, runner=_fake_runner())
    update_acceptor_yaml(acc_path, result, promote_to_verified=True)

    new_text = acc_path.read_text(encoding="utf-8")
    # Comments survive verbatim.
    assert "# integrity gate: do NOT delete this header comment." in new_text
    assert "# second comment line." in new_text
    # The literal-block command scalar is unchanged after reparse.
    reloaded = yaml.safe_load(new_text)
    assert reloaded["falsifier"]["command"] == original_command
    # The mutated fields took effect.
    assert reloaded["status"] == "VERIFIED"
    assert isinstance(reloaded["evidence_sha256"], list)
