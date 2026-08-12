import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.ci import pr_preflight


REQUIRED_CHECK_IDS = [
    "pip_bootstrap",
    "project_dependencies",
    "ruff",
    "black",
    "mypy",
    "detect_secrets",
    "quick_tests",
    "coverage_artifact",
]


def _write_executable(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable} -S\n{body}", encoding="utf-8")
    path.chmod(0o755)
    return path


def _write_tool_stub(bin_dir: Path, name: str, env_prefix: str) -> Path:
    body = f"""
import os
import sys

sys.stdout.write(os.environ.get("{env_prefix}_STDOUT", "{name}-stdout\\n"))
sys.stderr.write(os.environ.get("{env_prefix}_STDERR", "{name}-stderr\\n"))
sys.exit(int(os.environ.get("{env_prefix}_EXIT", "0")))
"""
    return _write_executable(bin_dir / name, body)


def _write_python_stub(bin_dir: Path) -> Path:
    body = """
import os
import sys

sys.stdout.write("python-stdout\\n")
sys.stderr.write("python-stderr\\n")
if "-m" in sys.argv and "pip" in sys.argv and "--upgrade" in sys.argv:
    sys.exit(int(os.environ.get("STUB_PIP_BOOTSTRAP_EXIT", "0")))
sys.exit(int(os.environ.get("STUB_PROJECT_INSTALL_EXIT", "0")))
"""
    return _write_executable(bin_dir / "python", body)


def _write_git_stub(bin_dir: Path, files: tuple[str, ...]) -> Path:
    body = f"""
import sys

if "ls-files" in sys.argv[1:]:
    sys.stdout.write("\\0".join({list(files)!r}))
sys.exit(0)
"""
    return _write_executable(bin_dir / "git", body)


def _prepare_repo(
    tmp_path: Path,
    monkeypatch,
    detect_secrets: bool = False,
    omit_tools: tuple[str, ...] = (),
    secrets_files: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'stub'\n", encoding="utf-8")
    (root / "tests").mkdir()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python_stub = _write_python_stub(bin_dir)
    for tool_name, env_prefix in (
        ("ruff", "STUB_RUFF"),
        ("black", "STUB_BLACK"),
        ("mypy", "STUB_MYPY"),
        ("pytest", "STUB_PYTEST"),
    ):
        if tool_name not in omit_tools:
            _write_tool_stub(bin_dir, tool_name, env_prefix)
    if detect_secrets:
        _write_tool_stub(bin_dir, "detect-secrets-hook", "STUB_DETECT_SECRETS")
    if secrets_files:
        (root / ".github").mkdir(parents=True, exist_ok=True)
        (root / ".github" / "detect-secrets.baseline").write_text("{}\n", encoding="utf-8")
        _write_git_stub(bin_dir, secrets_files)

    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("PR_PREFLIGHT_PYTHON", str(python_stub))
    return root, root / "artifacts" / "pr_preflight"


def _run_engine(root: Path, report_dir: Path) -> tuple[int, dict]:
    exit_code = pr_preflight.main(["--root", str(root), "--report-dir", str(report_dir)])
    report = json.loads((report_dir / "preflight_report.json").read_text(encoding="utf-8"))
    return exit_code, report


def _check(report: dict, check_id: str) -> dict:
    return next(check for check in report["checks"] if check["id"] == check_id)


def test_registry_contains_required_ids_and_log_paths(tmp_path, monkeypatch):
    root, _ = _prepare_repo(tmp_path, monkeypatch)

    specs = pr_preflight.build_check_registry(root)

    assert [spec.id for spec in specs] == REQUIRED_CHECK_IDS
    for spec in specs:
        assert spec.stdout_log == f"logs/{spec.id}.stdout.log"
        assert spec.stderr_log == f"logs/{spec.id}.stderr.log"
        assert spec.timeout_seconds > 0
        assert spec.success_exit_codes == [0]


def test_engine_passes_when_all_critical_stubs_pass(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 0
    assert report["status"] == "PASS"
    assert report["failure_count"] == 0
    assert _check(report, "detect_secrets")["status"] == "SKIPPED_OPTIONAL"


def test_engine_fails_when_ruff_fails(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_RUFF_EXIT", "2")

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert _check(report, "ruff")["status"] == "FAIL"


def test_engine_fails_when_mypy_fails(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_MYPY_EXIT", "2")

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert _check(report, "mypy")["status"] == "FAIL"


def test_engine_fails_when_pytest_fails(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_PYTEST_EXIT", "2")

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert _check(report, "quick_tests")["status"] == "FAIL"


def test_engine_fails_when_project_dependency_install_fails(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_PROJECT_INSTALL_EXIT", "19")

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert _check(report, "pip_bootstrap")["status"] == "PASS"
    assert _check(report, "project_dependencies")["status"] == "FAIL"


def test_engine_skips_detect_secrets_when_hook_missing(tmp_path, monkeypatch):
    # Surface files + baseline exist, so a command is built, but the
    # detect-secrets-hook executable is absent → optional skip (not blocked).
    root, report_dir = _prepare_repo(
        tmp_path, monkeypatch, detect_secrets=False, secrets_files=("core/sample.py",)
    )

    exit_code, report = _run_engine(root, report_dir)

    detect = _check(report, "detect_secrets")
    assert exit_code == 0
    assert detect["status"] == "SKIPPED_OPTIONAL"
    assert detect["critical"] is False
    assert detect["tool_available"] is False


def test_engine_skips_detect_secrets_when_no_surface_files(tmp_path, monkeypatch):
    # No baseline / no git-tracked surface files → empty command → clean skip,
    # never a stale `scan` that would silently pass on a new secret.
    root, report_dir = _prepare_repo(tmp_path, monkeypatch, detect_secrets=True)

    exit_code, report = _run_engine(root, report_dir)

    detect = _check(report, "detect_secrets")
    assert exit_code == 0
    assert detect["status"] == "SKIPPED_OPTIONAL"


def test_engine_uses_baseline_hook_not_scan(tmp_path, monkeypatch):
    # The command must mirror the CI gate: detect-secrets-hook + canonical
    # baseline + exclude (never `detect-secrets scan`, which exits 0 on a new
    # secret and would give a local false-green).
    root, _ = _prepare_repo(
        tmp_path, monkeypatch, detect_secrets=True, secrets_files=("core/sample.py",)
    )

    spec = next(s for s in pr_preflight.build_check_registry(root) if s.id == "detect_secrets")

    assert spec.command[0] == "detect-secrets-hook"
    assert "scan" not in spec.command
    assert "--baseline" in spec.command
    assert ".github/detect-secrets.baseline" in spec.command
    assert "--exclude-files" in spec.command
    assert "core/sample.py" in spec.command


def test_engine_fails_detect_secrets_when_present_and_failing(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(
        tmp_path, monkeypatch, detect_secrets=True, secrets_files=("core/sample.py",)
    )
    monkeypatch.setenv("STUB_DETECT_SECRETS_EXIT", "7")

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 1
    assert report["status"] == "FAIL"
    detect = _check(report, "detect_secrets")
    assert detect["critical"] is True
    assert detect["status"] == "FAIL"


def test_engine_blocks_when_critical_tool_is_missing(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch, omit_tools=("ruff",))

    exit_code, report = _run_engine(root, report_dir)

    ruff = _check(report, "ruff")
    assert exit_code == 1
    assert report["status"] == "BLOCKED"
    assert ruff["status"] == "BLOCKED"
    assert ruff["critical"] is True
    assert ruff["tool_available"] is False
    assert "required executable missing" in ruff["failure_reason"]


def test_engine_writes_report_json_on_failure(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_PYTEST_EXIT", "4")

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 1
    assert (report_dir / "preflight_report.json").exists()
    assert report["failure_count"] >= 1
    assert report["first_file_to_open"] == "artifacts/pr_preflight/preflight_report.json"


def test_engine_preserves_stdout_and_stderr_logs(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_RUFF_STDOUT", "ruff-out\n")
    monkeypatch.setenv("STUB_RUFF_STDERR", "ruff-err\n")

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 0
    ruff = _check(report, "ruff")
    assert (root / ruff["stdout_log"]).read_text(encoding="utf-8") == "ruff-out\n"
    assert (root / ruff["stderr_log"]).read_text(encoding="utf-8") == "ruff-err\n"


def test_engine_report_preserves_execution_metadata(tmp_path, monkeypatch):
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)

    exit_code, report = _run_engine(root, report_dir)

    assert exit_code == 0
    assert report["schema_version"] == 1
    assert report["status"] in pr_preflight.ALLOWED_FINAL_STATUSES
    for check in report["checks"]:
        assert check["status"] in pr_preflight.ALLOWED_CHECK_STATUSES
        assert check["cwd"] == "."
        assert check["timeout_seconds"] > 0
        assert check["success_exit_codes"] == [0]
        assert check["stdout_log"].endswith(f"{check['id']}.stdout.log")
        assert check["stderr_log"].endswith(f"{check['id']}.stderr.log")


def test_shell_wrapper_forwards_python_runner_exit_code(tmp_path):
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    bin_dir = tmp_path / "bin"
    scripts_dir.mkdir(parents=True)
    bin_dir.mkdir()
    source_wrapper = Path(__file__).resolve().parents[2] / "scripts" / "test-pr-locally.sh"
    target_wrapper = scripts_dir / "test-pr-locally.sh"
    target_wrapper.write_text(source_wrapper.read_text(encoding="utf-8"), encoding="utf-8")
    target_wrapper.chmod(0o755)
    _write_executable(bin_dir / "python3", "import sys\nsys.exit(37)\n")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

    result = subprocess.run(
        ["bash", str(target_wrapper)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 37
    # The stub wrote no report, so the wrapper must NOT advertise a
    # non-existent evidence artifact (fail-closed triage on the BLOCKED path).
    assert "FIRST_FILE_TO_OPEN=" not in result.stdout


def test_shell_wrapper_prints_first_file_only_when_report_written(tmp_path):
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    bin_dir = tmp_path / "bin"
    scripts_dir.mkdir(parents=True)
    bin_dir.mkdir()
    source_wrapper = Path(__file__).resolve().parents[2] / "scripts" / "test-pr-locally.sh"
    target_wrapper = scripts_dir / "test-pr-locally.sh"
    target_wrapper.write_text(source_wrapper.read_text(encoding="utf-8"), encoding="utf-8")
    target_wrapper.chmod(0o755)
    # A stub that serves both python invocations the wrapper makes: the
    # preflight runner (writes the report) and the inference-ledger appender
    # (no --report-dir; just succeeds). Both must exit 0 so the wrapper reaches
    # the FIRST_FILE_TO_OPEN print on the report-written path.
    _write_executable(
        bin_dir / "python3",
        "import os, sys\n"
        "argv = sys.argv\n"
        "if '--report-dir' in argv:\n"
        "    rd = argv[argv.index('--report-dir') + 1]\n"
        "    os.makedirs(rd, exist_ok=True)\n"
        "    open(os.path.join(rd, 'preflight_report.json'), 'w').write('{}')\n"
        "sys.exit(0)\n",
    )
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

    result = subprocess.run(
        ["bash", str(target_wrapper)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert f"FIRST_FILE_TO_OPEN={repo}/artifacts/pr_preflight/preflight_report.json" in result.stdout


def test_exit_code_matches_final_status(tmp_path, monkeypatch):
    # REQ-PREFLIGHT-003: the process exit code is a pure function of the final
    # report status — PASS -> 0, FAIL -> 1, BLOCKED -> 1. Never a green exit on a
    # non-PASS report.
    pass_dir = tmp_path / "pass"
    pass_dir.mkdir()
    root, report_dir = _prepare_repo(pass_dir, monkeypatch)
    exit_code, report = _run_engine(root, report_dir)
    assert report["status"] == "PASS"
    assert exit_code == 0

    # BLOCKED: a critical tool is missing.
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    root, report_dir = _prepare_repo(blocked_dir, monkeypatch, omit_tools=("mypy",))
    exit_code, report = _run_engine(root, report_dir)
    assert report["status"] == "BLOCKED"
    assert exit_code == 1

    # FAIL: a critical check exits nonzero.
    fail_dir = tmp_path / "fail"
    fail_dir.mkdir()
    root, report_dir = _prepare_repo(fail_dir, monkeypatch)
    monkeypatch.setenv("STUB_RUFF_EXIT", "1")
    exit_code, report = _run_engine(root, report_dir)
    assert report["status"] == "FAIL"
    assert exit_code == 1


def test_critical_skipped_optional_is_impossible(tmp_path, monkeypatch):
    # REQ-PREFLIGHT-005: a SKIPPED_OPTIONAL check is never critical — neither in a
    # produced report (detect_secrets/coverage skip non-critically) nor as an
    # accepted shape (the contract refuses a forged critical optional skip).
    root, report_dir = _prepare_repo(tmp_path, monkeypatch)
    _, report = _run_engine(root, report_dir)

    skipped = [check for check in report["checks"] if check["status"] == "SKIPPED_OPTIONAL"]
    assert skipped, "expected at least one SKIPPED_OPTIONAL check (detect_secrets/coverage)"
    for check in report["checks"]:
        assert not (check["critical"] and check["status"] == "SKIPPED_OPTIONAL")

    forged = json.loads((report_dir / "preflight_report.json").read_text(encoding="utf-8"))
    target = next(check for check in forged["checks"] if check["status"] == "SKIPPED_OPTIONAL")
    target["critical"] = True
    with pytest.raises(ValueError):
        pr_preflight.validate_report_contract(forged)


def test_engine_blocks_when_report_cannot_be_written(tmp_path, monkeypatch, capsys):
    # REQ-PREFLIGHT-009: a report-write failure (report dir is a file) prints a
    # reason to stderr and exits nonzero — never a silent PASS.
    root, _ = _prepare_repo(tmp_path, monkeypatch)
    report_dir = tmp_path / "report_is_a_file"
    report_dir.write_text("", encoding="utf-8")

    exit_code = pr_preflight.main(["--root", str(root), "--report-dir", str(report_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "could not write evidence report" in captured.err
    assert "PR_PREFLIGHT_STATUS=PASS" not in captured.out
    assert report_dir.is_file()


def test_engine_blocks_invalid_root_and_writes_report(tmp_path, monkeypatch):
    # REQ-PREFLIGHT-009: a non-directory root yields a single invalid_root BLOCKED
    # check, a BLOCKED report, and a nonzero exit.
    bad_root = tmp_path / "not_a_dir"
    bad_root.write_text("", encoding="utf-8")
    report_dir = tmp_path / "out"

    exit_code = pr_preflight.main(["--root", str(bad_root), "--report-dir", str(report_dir)])
    report = json.loads((report_dir / "preflight_report.json").read_text(encoding="utf-8"))

    assert exit_code == 1
    assert report["status"] == "BLOCKED"
    assert [check["id"] for check in report["checks"]] == ["invalid_root"]
    check = report["checks"][0]
    assert check["status"] == "BLOCKED"
    assert check["critical"] is True
    assert report["failure_count"] == 1
