from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from tools.release_evidence_harness import (
    Gate,
    _default_gates,
    _run_gate,
    _write_release_gate_yaml,
)


def test_run_gate_records_raw_log_and_exit_code(tmp_path: Path) -> None:
    result = _run_gate(
        Gate("sample", [sys.executable, "-c", "print('hello evidence')"]),
        tmp_path / "logs",
        timeout_sec=10,
    )

    assert result.exit_code == 0
    assert result.status == "GREEN"
    assert result.evidence_sha256 is not None
    assert result.evidence_bytes > 0
    log = result.evidence.read_text(encoding="utf-8")
    assert "hello evidence" in log
    assert "exit_code=0" in log
    assert "started_utc=" in log
    assert "finished_utc=" in log


def test_run_gate_marks_non_empty_output_red_when_semantic_empty_required(tmp_path: Path) -> None:
    result = _run_gate(
        Gate("dirty", [sys.executable, "-c", "print('dirty')"], fail_on_output=True),
        tmp_path / "logs",
        timeout_sec=10,
    )

    assert result.exit_code == 1
    assert result.status == "RED"
    assert result.semantic_failure == "non-empty output is a release-blocking semantic failure"
    assert "SEMANTIC_FAILURE" in result.evidence.read_text(encoding="utf-8")


def test_release_gate_yaml_contains_command_evidence_exit_code_and_semantic_failure(
    tmp_path: Path,
) -> None:
    result = _run_gate(
        Gate("sample", [sys.executable, "-c", "import json; print(json.dumps({'ok': True}))"]),
        tmp_path / "logs",
        timeout_sec=10,
    )
    release_gate = tmp_path / "release_gate.yaml"

    _write_release_gate_yaml(release_gate, [result])

    text = release_gate.read_text(encoding="utf-8")
    assert "schema_version: 1" in text
    assert "name: \"sample\"" in text
    assert "status: \"GREEN\"" in text
    assert "exit_code: 0" in text
    assert "semantic_failure: null" in text
    assert "evidence_sha256:" in text
    assert "evidence_bytes:" in text
    assert result.evidence.as_posix() in text


def test_default_gates_make_clean_install_and_clean_tree_required() -> None:
    gates = _default_gates("python", "python3.12", skip_clean_install=False)

    assert gates[0].name == "clean_install"
    assert {gate.name for gate in gates[:3]} == {
        "clean_install",
        "diff_summary_clean",
        "working_tree_clean",
    }
    assert next(gate for gate in gates if gate.name == "diff_summary_clean").fail_on_output
    assert next(gate for gate in gates if gate.name == "working_tree_clean").fail_on_output


def test_skip_clean_install_is_explicit_opt_out() -> None:
    gates = _default_gates("python", "python3.12", skip_clean_install=True)

    assert "clean_install" not in {gate.name for gate in gates}


def test_fixed_clock_makes_gate_evidence_hash_stable(tmp_path: Path) -> None:
    fixed_clock = lambda: "2026-01-01T00:00:00Z"
    gate = Gate("stable", [sys.executable, "-c", "print('stable')"])

    first = _run_gate(gate, tmp_path / "one", timeout_sec=10, clock=fixed_clock)
    second = _run_gate(gate, tmp_path / "two", timeout_sec=10, clock=fixed_clock)

    assert first.evidence_sha256 == second.evidence_sha256
    assert first.evidence_bytes == second.evidence_bytes
    assert "started_utc=2026-01-01T00:00:00Z" in first.evidence.read_text(encoding="utf-8")


def test_main_manifest_reports_valid_gates_and_fixed_timestamp(tmp_path: Path, monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(
        harness,
        "_default_gates",
        lambda python, clean_python, skip_clean_install: [
            Gate("ok", [sys.executable, "-c", "print('ok')"]),
            Gate("dirty", [sys.executable, "-c", "print('dirty')"], fail_on_output=True),
        ],
    )
    evidence_dir = tmp_path / "evidence"
    release_gate = tmp_path / "release_gate.yaml"

    exit_code = harness.main([
        "--evidence-dir",
        str(evidence_dir),
        "--release-gate",
        str(release_gate),
        "--fixed-timestamp-utc",
        "2026-01-01T00:00:00Z",
        "--allow-failures",
    ])

    assert exit_code == 0
    manifest = __import__("json").loads((evidence_dir / "manifest.json").read_text())
    assert manifest["generated_utc"] == "2026-01-01T00:00:00Z"
    assert manifest["deterministic_timestamp_utc"] == "2026-01-01T00:00:00Z"
    assert manifest["valid_gates"] == ["ok"]
    assert manifest["failed_required"] == ["dirty"]
    assert "generated_utc: \"2026-01-01T00:00:00Z\"" in release_gate.read_text(encoding="utf-8")


def test_default_python_prefers_current_interpreter(monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(harness.shutil, "which", lambda candidate: candidate)

    assert harness._default_python() == sys.executable


def test_invalid_fixed_timestamp_is_rejected(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    exit_code = harness.main([
        "--evidence-dir",
        str(tmp_path / "evidence"),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--fixed-timestamp-utc",
        "not-a-time",
    ])

    assert exit_code == 2


def test_large_output_is_truncated_and_marked_red(tmp_path: Path) -> None:
    result = _run_gate(
        Gate("large", [sys.executable, "-c", "print('x' * 200)"]),
        tmp_path / "logs",
        timeout_sec=10,
        max_log_bytes=40,
    )

    assert result.exit_code == 1
    assert result.status == "RED"
    assert result.output_truncated is True
    assert result.semantic_failure == "command output exceeded max log bytes"
    assert "LOG_TRUNCATED after 40 bytes" in result.evidence.read_text(encoding="utf-8")


def test_clean_install_command_quotes_clean_python() -> None:
    from tools.release_evidence_harness import _clean_install_command

    command = _clean_install_command("/tmp/python with spaces")

    assert "'/tmp/python with spaces' -m venv" in command[2]


def test_verify_evidence_manifest_accepts_generated_bundle(tmp_path: Path, monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(
        harness,
        "_default_gates",
        lambda python, clean_python, skip_clean_install: [
            Gate("ok", [sys.executable, "-c", "print('ok')"]),
        ],
    )
    evidence_dir = tmp_path / "evidence"
    assert harness.main([
        "--evidence-dir",
        str(evidence_dir),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--fixed-timestamp-utc",
        "2026-01-01T00:00:00Z",
    ]) == 0

    assert harness.verify_evidence_manifest(evidence_dir / "manifest.json") == []
    assert harness.main(["--verify-manifest", str(evidence_dir / "manifest.json")]) == 0


def test_verify_evidence_manifest_rejects_tampered_log(tmp_path: Path, monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(
        harness,
        "_default_gates",
        lambda python, clean_python, skip_clean_install: [
            Gate("ok", [sys.executable, "-c", "print('ok')"]),
        ],
    )
    evidence_dir = tmp_path / "evidence"
    assert harness.main([
        "--evidence-dir",
        str(evidence_dir),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--fixed-timestamp-utc",
        "2026-01-01T00:00:00Z",
    ]) == 0
    (evidence_dir / "raw_logs" / "ok.log").write_text("tampered\n", encoding="utf-8")

    errors = harness.verify_evidence_manifest(evidence_dir / "manifest.json")

    assert any("evidence_sha256 mismatch" in error for error in errors)
    assert harness.main(["--verify-manifest", str(evidence_dir / "manifest.json")]) == 1


def test_verify_evidence_manifest_rejects_inconsistent_gate_lists(tmp_path: Path, monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(
        harness,
        "_default_gates",
        lambda python, clean_python, skip_clean_install: [
            Gate("ok", [sys.executable, "-c", "print('ok')"]),
        ],
    )
    evidence_dir = tmp_path / "evidence"
    assert harness.main([
        "--evidence-dir",
        str(evidence_dir),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--fixed-timestamp-utc",
        "2026-01-01T00:00:00Z",
    ]) == 0
    manifest_path = evidence_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["valid_gates"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = harness.verify_evidence_manifest(manifest_path)

    assert "valid_gates does not match result exit codes" in errors


def test_gate_name_path_traversal_is_rejected(tmp_path: Path) -> None:
    try:
        _run_gate(Gate("../escape", [sys.executable, "-c", "print('bad')"]), tmp_path, 10)
    except ValueError as exc:
        assert "invalid gate name" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("path traversal gate name was accepted")


def test_command_and_output_secrets_are_redacted(tmp_path: Path) -> None:
    result = _run_gate(
        Gate(
            "secret",
            [
                sys.executable,
                "-c",
                "print('token=abc123 Authorization: Bearer secret-token')",
                "password=from-command",
            ],
        ),
        tmp_path / "logs",
        timeout_sec=10,
    )

    log = result.evidence.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "abc123" not in log
    assert "secret-token" not in log
    assert "from-command" not in log
    assert "[REDACTED]" in log


def test_symlinked_raw_logs_directory_is_refused(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    evidence_dir = tmp_path / "evidence"
    target = tmp_path / "target"
    target.mkdir()
    evidence_dir.mkdir()
    (evidence_dir / "raw_logs").symlink_to(target, target_is_directory=True)

    exit_code = harness.main([
        "--evidence-dir",
        str(evidence_dir),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--skip-clean-install",
        "--allow-tainted-env",
    ])

    assert exit_code == 2
    assert target.exists()


def test_verify_evidence_manifest_rejects_evidence_path_escape(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    outside = tmp_path / "outside.log"
    outside.write_text("outside", encoding="utf-8")
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "generated_utc": "2026-01-01T00:00:00Z",
        "results": [
            {
                "name": "escape",
                "status": "GREEN",
                "required": True,
                "exit_code": 0,
                "evidence": "../outside.log",
                "started_utc": "2026-01-01T00:00:00Z",
                "finished_utc": "2026-01-01T00:00:00Z",
                "evidence_sha256": digest,
                "evidence_bytes": outside.stat().st_size,
            }
        ],
        "valid_gates": ["escape"],
        "failed_required": [],
    }
    manifest_path = tmp_path / "bundle" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = harness.verify_evidence_manifest(manifest_path)

    assert any("evidence path escapes bundle" in error for error in errors)


def test_verify_evidence_manifest_rejects_symlinked_evidence_file(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    bundle = tmp_path / "bundle"
    raw_logs = bundle / "raw_logs"
    raw_logs.mkdir(parents=True)
    target = raw_logs / "target.log"
    target.write_text("inside", encoding="utf-8")
    evidence = raw_logs / "ok.log"
    evidence.symlink_to(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "generated_utc": "2026-01-01T00:00:00Z",
        "results": [
            {
                "name": "ok",
                "status": "GREEN",
                "required": True,
                "exit_code": 0,
                "evidence": "raw_logs/ok.log",
                "started_utc": "2026-01-01T00:00:00Z",
                "finished_utc": "2026-01-01T00:00:00Z",
                "evidence_sha256": digest,
                "evidence_bytes": target.stat().st_size,
            }
        ],
        "valid_gates": ["ok"],
        "failed_required": [],
    }
    manifest_path = bundle / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = harness.verify_evidence_manifest(manifest_path)

    assert any("refusing symlinked evidence file" in error for error in errors)


def test_verify_evidence_manifest_rejects_symlinked_raw_logs_dir(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    bundle = tmp_path / "bundle"
    target = tmp_path / "target"
    bundle.mkdir()
    target.mkdir()
    (bundle / "raw_logs").symlink_to(target, target_is_directory=True)
    manifest_path = bundle / "manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "generated_utc": "2026-01-01T00:00:00Z", "results": []}),
        encoding="utf-8",
    )

    errors = harness.verify_evidence_manifest(manifest_path)

    assert any("refusing symlinked raw_logs directory" in error for error in errors)


def test_release_bundle_contains_sbom_audit_telemetry_and_ci_status(tmp_path: Path, monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(
        harness,
        "_default_gates",
        lambda python, clean_python, skip_clean_install: [
            Gate("ok", [sys.executable, "-c", "print('ok')"]),
        ],
    )
    evidence_dir = tmp_path / "evidence"

    assert harness.main([
        "--evidence-dir",
        str(evidence_dir),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--fixed-timestamp-utc",
        "2026-01-01T00:00:00Z",
        "--ci",
    ]) == 0

    manifest = json.loads((evidence_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution_mode"] == "asyncio"
    assert manifest["ci"] is True
    assert manifest["sbom"]["format"] == "CycloneDX"
    assert (evidence_dir / "sbom.cdx.json").is_file()
    assert (evidence_dir / "audit_report.pdf").read_bytes().startswith(b"%PDF-1.4")
    assert "geosync_release_gate_status" in (evidence_dir / "telemetry" / "release_gates.prom").read_text(encoding="utf-8")
    assert (evidence_dir / "telemetry" / "datadog_events.json").is_file()
    assert json.loads((evidence_dir / "ci_status.json").read_text(encoding="utf-8"))["release_status"] == "PASS"
    assert harness.verify_evidence_manifest(evidence_dir / "manifest.json") == []


def test_environment_baseline_drift_blocks_gate(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    baseline = {"gate_environment_sha256": {"ok": "0" * 64}}
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    result = harness._run_gate(
        Gate("ok", [sys.executable, "-c", "print('executed-drifted-command')"]),
        tmp_path / "logs",
        timeout_sec=10,
        environment_baseline=harness._load_environment_baseline(baseline_path),
    )

    assert result.status == "RED"
    assert result.environment_status == "DRIFT"
    assert result.semantic_failure == "environment fingerprint drift before gate execution"
    assert "ENVIRONMENT_DRIFT" in result.evidence.read_text(encoding="utf-8")


def test_gpg_manifest_signature_can_be_required(tmp_path: Path, monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(
        harness,
        "_default_gates",
        lambda python, clean_python, skip_clean_install: [
            Gate("ok", [sys.executable, "-c", "print('ok')"]),
        ],
    )
    fake_gpg = tmp_path / "gpg"
    fake_gpg.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "if '--verify' in sys.argv:\n"
        "    raise SystemExit(0)\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "out.write_text('fake-detached-signature', encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_gpg.chmod(0o755)
    monkeypatch.setattr(harness, "GPG_BINARY_ALLOWLIST", {fake_gpg.resolve().as_posix()})
    evidence_dir = tmp_path / "evidence"

    assert harness.main([
        "--evidence-dir",
        str(evidence_dir),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--fixed-timestamp-utc",
        "2026-01-01T00:00:00Z",
        "--gpg-binary",
        str(fake_gpg),
        "--gpg-key",
        "release@example.invalid",
    ]) == 0

    assert (evidence_dir / "manifest.json.asc").is_file()
    assert harness.main([
        "--verify-manifest",
        str(evidence_dir / "manifest.json"),
        "--require-gpg-signature",
        "--gpg-binary",
        str(fake_gpg),
    ]) == 0


def test_async_gate_runner_executes_independent_gates_concurrently(tmp_path: Path) -> None:
    from time import monotonic
    from tools import release_evidence_harness as harness

    gates = [
        Gate("one", [sys.executable, "-c", "import time; time.sleep(0.3); print('one')"]),
        Gate("two", [sys.executable, "-c", "import time; time.sleep(0.3); print('two')"]),
    ]
    start = monotonic()
    results = harness._run_gates(gates, tmp_path / "logs", 10, lambda: "2026-01-01T00:00:00Z", 1000)
    elapsed = monotonic() - start

    assert [result.status for result in results] == ["GREEN", "GREEN"]
    assert elapsed < 0.55


def test_timestamp_range_rejects_underflow_and_overflow() -> None:
    from tools import release_evidence_harness as harness

    for value in ("2025-12-31T23:59:59Z", "2030-01-01T00:00:01Z"):
        try:
            harness._validate_utc_timestamp(value)
        except ValueError as exc:
            assert "supported release evidence range" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError(f"out-of-range timestamp accepted: {value}")

    assert harness._validate_utc_timestamp("2026-01-01T00:00:00Z") == "2026-01-01T00:00:00Z"
    assert harness._validate_utc_timestamp("2030-01-01T00:00:00Z") == "2030-01-01T00:00:00Z"


def test_high_entropy_tokens_are_redacted(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    secret = "QWxhZGRpbjpvcGVuIHNlc2FtZTEyMzQ1Njc4OTA="  # pragma: allowlist secret
    result = harness._run_gate(
        Gate("entropy", [sys.executable, "-c", f"print('{secret}')"]),
        tmp_path / "logs",
        timeout_sec=10,
    )

    log = result.evidence.read_text(encoding="utf-8")
    assert result.status == "GREEN"
    assert secret not in log
    assert "[REDACTED]" in log


def test_environment_fingerprint_sorts_file_records(monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(harness, "_file_sha256", lambda path: (path.name, 1))
    first = harness._environment_fingerprint([sys.executable])
    second = harness._environment_fingerprint([sys.executable])

    assert first["sha256"] == second["sha256"]
    paths = [item["path"] for item in first["payload"]["files"]]
    assert paths == sorted(paths)


def test_duplicate_gate_names_are_rejected_for_parallel_execution(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    try:
        harness._run_gates(
            [Gate("dup", [sys.executable, "-c", "print(1)"]), Gate("dup", [sys.executable, "-c", "print(2)"])],
            tmp_path / "logs",
            10,
            lambda: "2026-01-01T00:00:00Z",
            1000,
        )
    except ValueError as exc:
        assert "duplicate gate names" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("duplicate gate names were accepted")


def test_skip_clean_install_requires_tainted_dev_opt_in(tmp_path: Path, monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(harness, "_default_gates", lambda python, clean_python, skip_clean_install: [])

    assert harness.main([
        "--evidence-dir",
        str(tmp_path / "evidence"),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--skip-clean-install",
    ]) == 2


def test_skip_clean_install_is_forbidden_in_ci_even_with_tainted_opt_in(tmp_path: Path, monkeypatch) -> None:
    from tools import release_evidence_harness as harness

    monkeypatch.setattr(harness, "_default_gates", lambda python, clean_python, skip_clean_install: [])

    assert harness.main([
        "--evidence-dir",
        str(tmp_path / "evidence"),
        "--release-gate",
        str(tmp_path / "release_gate.yaml"),
        "--skip-clean-install",
        "--allow-tainted-env",
        "--ci",
    ]) == 2


def test_gpg_binary_outside_allowlist_is_rejected(tmp_path: Path) -> None:
    from tools import release_evidence_harness as harness

    fake_gpg = tmp_path / "gpg"
    fake_gpg.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_gpg.chmod(0o755)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    signed, _sha, error = harness._sign_manifest(
        manifest, tmp_path / "manifest.json.asc", gpg_binary=fake_gpg.as_posix(), gpg_key="x"
    )

    assert signed is False
    assert error is not None and "allowlist" in error
