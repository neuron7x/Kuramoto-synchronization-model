from __future__ import annotations

from pathlib import Path

from tools.compliance.secret_scanner import SecretScanner


def test_secret_scanner_detects_api_key(tmp_path: Path) -> None:
    target = tmp_path / "config.env"
    target.write_text("API_KEY=ABCD1234ABCDEFGHIJKLMNOPQRSTUV", encoding="utf-8")
    scanner = SecretScanner(min_entropy=3.5, min_length=20)
    findings = scanner.scan(tmp_path)
    assert findings
    assert any(f.detector == "generic_api_key" for f in findings)


def test_secret_scanner_honors_ignore_file(tmp_path: Path) -> None:
    (tmp_path / ".secretsignore").write_text("config.env\n", encoding="utf-8")
    (tmp_path / "config.env").write_text(
        "API_KEY=ABCD1234ABCDEFGHIJKLMNOPQRSTUV", encoding="utf-8"
    )
    scanner = SecretScanner(min_entropy=3.5, min_length=20)
    findings = scanner.scan(tmp_path)
    assert not findings
