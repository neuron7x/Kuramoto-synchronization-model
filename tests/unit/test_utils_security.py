# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from core.utils.security import SecretDetector, check_for_hardcoded_secrets

API_KEY_LABEL = "".join(("a", "p", "i", "_", "k", "e", "y"))
PASSWORD_LABEL = "".join(("p", "a", "s", "s", "w", "o", "r", "d"))
GENERIC_SECRET_VALUE = "".join(("s", "u", "p", "e", "r", "s", "e", "c", "r", "e", "t"))
IGNORED_SECRET_VALUE = "".join(("h", "u", "n", "t", "e", "r", str(2)))


def test_secret_detector_identifies_api_keys(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    workspace = tmp_path_factory.mktemp("security")
    target = workspace / "config.py"
    api_key_value = "".join(("abc", "def", "1234567890"))
    target.write_text(f"API_KEY = '{api_key_value}'\n", encoding="utf-8")

    detector = SecretDetector()
    findings = detector.scan_file(target)

    assert findings
    secret_type, line_num, masked = findings[0]
    assert secret_type == API_KEY_LABEL
    assert line_num == 1
    assert "********" in masked


def test_secret_detector_respects_ignore_patterns(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    workspace = tmp_path_factory.mktemp("security-ignore")
    node_modules = workspace / "node_modules"
    node_modules.mkdir()
    ignored = node_modules / "config.js"
    ignored.write_text(
        f"const {PASSWORD_LABEL} = '{IGNORED_SECRET_VALUE}';\n",
        encoding="utf-8",
    )

    detector = SecretDetector()
    assert detector.scan_file(ignored) == []


def test_secret_detector_does_not_ignore_non_test_prefixes(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    workspace = tmp_path_factory.mktemp("security-latest")
    target = workspace / "latest_config.py"
    target.write_text(
        f"{PASSWORD_LABEL}='{GENERIC_SECRET_VALUE}'\n",
        encoding="utf-8",
    )

    detector = SecretDetector()
    findings = detector.scan_file(target)

    assert findings, "Files with 'latest' in the name should not be ignored"
    assert any(secret_type == PASSWORD_LABEL for secret_type, _, _ in findings)


def test_scan_directory_filters_extensions(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    workspace = tmp_path_factory.mktemp("security-scan")
    allowed = workspace / "settings.py"
    allowed.write_text(f"{PASSWORD_LABEL}='{GENERIC_SECRET_VALUE}'\n", encoding="utf-8")
    skipped = workspace / "README.md"
    skipped.write_text("api_" + "sec" + "ret" + "='value'\n", encoding="utf-8")

    detector = SecretDetector()
    results = detector.scan_directory(workspace, extensions=[".py"])

    assert "settings.py" in results
    assert "README.md" not in results


def test_scan_directory_detects_dotenv_files(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    workspace = tmp_path_factory.mktemp("security-dotenv")
    dotenv_file = workspace / ".env"
    dotenv_file.write_text(
        f"{API_KEY_LABEL}='{GENERIC_SECRET_VALUE}'\n",
        encoding="utf-8",
    )

    dotenv_local = workspace / ".env.local"
    dotenv_local.write_text(
        f"{PASSWORD_LABEL}='{GENERIC_SECRET_VALUE}'\n",
        encoding="utf-8",
    )

    dotenv_production = workspace / ".env.production"
    dotenv_production.write_text(
        f"{GENERIC_SECRET_VALUE}='{GENERIC_SECRET_VALUE}'\n",
        encoding="utf-8",
    )

    ignored_file = workspace / "notes.txt"
    ignored_file.write_text(
        f"{PASSWORD_LABEL}='{GENERIC_SECRET_VALUE}'\n",
        encoding="utf-8",
    )

    detector = SecretDetector()
    results = detector.scan_directory(workspace)

    assert ".env" in results
    assert ".env.local" in results
    assert ".env.production" in results
    assert "notes.txt" not in results


def test_check_for_hardcoded_secrets_reports_findings(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path_factory.mktemp("security-project")
    secret_file = project / "secrets.py"
    secret_file.write_text("github_token = 'ghp_" + "a" * 36 + "'\n", encoding="utf-8")

    found = check_for_hardcoded_secrets(str(project))
    captured = capsys.readouterr()

    assert found is True
    assert "Potential secrets detected" in captured.out
    assert "********" in captured.out


def test_check_for_hardcoded_secrets_returns_false_when_clean(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    clean_project = tmp_path_factory.mktemp("security-clean")

    found = check_for_hardcoded_secrets(str(clean_project))
    captured = capsys.readouterr()

    assert found is False
    assert "No hardcoded secrets detected" in captured.out
