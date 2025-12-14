# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import builtins
import re
import tempfile
from pathlib import Path

import pytest

from core.utils.security import SecretDetector, check_for_hardcoded_secrets

# Test fixture for private key content
_TEST_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nfake-key-data\n-----END PRIVATE KEY-----"


def test_secret_detector_ignores_dev_tls_certs(tmp_path: Path) -> None:
    """Test that dev TLS certificates are ignored."""
    tls_dir = tmp_path / "configs" / "tls" / "dev"
    tls_dir.mkdir(parents=True)
    cert_file = tls_dir / "server.key.pem"
    cert_file.write_text(_TEST_PRIVATE_KEY, encoding="utf-8")

    detector = SecretDetector()
    findings = detector.scan_file(cert_file)
    assert findings == [], "Dev TLS certificates should be ignored"


def test_secret_detector_ignores_audit_artifacts(tmp_path: Path) -> None:
    """Test that audit artifacts are ignored."""
    audit_dir = tmp_path / "audit" / "artifacts"
    audit_dir.mkdir(parents=True)
    report = audit_dir / "gitleaks.json"
    report.write_text('{"secret": "should-be-ignored"}', encoding="utf-8")

    detector = SecretDetector()
    findings = detector.scan_file(report)
    assert findings == [], "Audit artifacts should be ignored"


def test_secret_detector_detects_production_tls_certs(tmp_path: Path) -> None:
    """Test that production TLS certificates are NOT ignored."""
    tls_dir = tmp_path / "configs" / "tls" / "production"
    tls_dir.mkdir(parents=True)
    cert_file = tls_dir / "server.key.pem"
    cert_file.write_text(_TEST_PRIVATE_KEY, encoding="utf-8")

    detector = SecretDetector()
    findings = detector.scan_file(cert_file)
    assert len(findings) > 0, "Production TLS certificates should be detected"


def test_secret_detector_masks_findings() -> None:
    workspace = Path(tempfile.mkdtemp(prefix="secretdetector"))
    target = workspace / "config.py"
    target.write_text(
        "API_KEY = 'abcd1234'\npassword='verysecretvalue'\n", encoding="utf-8"
    )

    detector = SecretDetector()
    findings = detector.scan_file(target)
    assert findings, "Expected secret patterns to be detected"
    for secret_type, line_num, masked in findings:
        assert secret_type in {"api_key", "password"}
        assert line_num in {1, 2}
        assert "abcd1234" not in masked
        assert "verysecretvalue" not in masked
        assert "********" in masked


def test_secret_detector_ignores_documentation(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    ignored = docs_dir / "secrets.md"
    ignored.write_text("password: should-not-be-detected", encoding="utf-8")

    detector = SecretDetector()
    assert detector.scan_file(ignored) == []


def test_secret_detector_accepts_custom_patterns(tmp_path: Path) -> None:
    token_pattern = re.compile(r"custom_token\s*=\s*'([0-9a-f]{8})'")
    detector = SecretDetector(custom_patterns={"custom": token_pattern})

    workspace = Path(tempfile.mkdtemp(prefix="custompattern"))
    target = workspace / "custom.txt"
    target.write_text("custom_token='deadbeef'", encoding="utf-8")

    findings = detector.scan_file(target)
    assert any(secret_type == "custom" for secret_type, *_ in findings)


def test_scan_file_handles_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that unreadable files are handled gracefully."""
    workspace = Path(tempfile.mkdtemp(prefix="unreadable"))
    target = workspace / "secrets.env"
    target.write_text("API_SECRET='hidden'", encoding="utf-8")

    original_open = builtins.open

    def raising_open(*args, **kwargs):
        if Path(args[0]) == target:
            raise OSError("permission denied")
        return original_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", raising_open)

    detector = SecretDetector()
    findings = detector.scan_file(target)

    # Unreadable files should return empty findings without crashing
    assert findings == []


def test_scan_directory_respects_extension_filter() -> None:
    repo = Path(tempfile.mkdtemp(prefix="secdir"))
    (repo / "config.yaml").write_text(
        "secret: 'should-be-detected'\n", encoding="utf-8"
    )
    (repo / "image.png").write_bytes(b"binary-data")

    detector = SecretDetector()
    results = detector.scan_directory(repo, extensions=[".yaml", ".json"])
    assert "config.yaml" in results
    assert "image.png" not in results


def test_scan_directory_skips_non_files_and_empty_extension_list(
    tmp_path: Path,
) -> None:
    repo = Path(tempfile.mkdtemp(prefix="secrepo"))
    nested = repo / "configs"
    nested.mkdir()
    (nested / "secret.env").write_text("API_KEY='abcdef123456'", encoding="utf-8")
    (nested / "notes.txt").write_text("no sensitive data", encoding="utf-8")

    detector = SecretDetector()
    results = detector.scan_directory(repo, extensions=[])

    assert "configs/secret.env" in results
    assert "configs/notes.txt" not in results


def test_check_for_hardcoded_secrets_reports_findings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = Path(tempfile.mkdtemp(prefix="secretrepo"))
    env_file = workspace / "service.env"
    env_file.write_text('API_SECRET="supersecretvalue"\n', encoding="utf-8")

    found = check_for_hardcoded_secrets(str(workspace))
    captured = capsys.readouterr()

    assert found is True
    assert "Potential secrets" in captured.out
    assert "supersecretvalue" not in captured.out
    assert "********" in captured.out


def test_check_for_hardcoded_secrets_returns_false_when_clean(
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = Path(tempfile.mkdtemp(prefix="cleanrepo"))
    (workspace / "README.md").write_text("no secrets here", encoding="utf-8")

    found = check_for_hardcoded_secrets(str(workspace))
    captured = capsys.readouterr()

    assert found is False
    assert "No hardcoded secrets" in captured.out
