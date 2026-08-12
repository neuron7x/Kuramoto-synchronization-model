# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth-and-clean-tree contract for the SEC-006 secret-boundary gate.

A secret scanner earns trust only by two symmetric proofs:

  * POSITIVE — on the real, clean working tree the gate exits 0 (no high-confidence
    secret; ``.env.example`` is placeholder-only; the scanner reports teeth).
  * NEGATIVE — fed a planted fake credential (non-example AWS key + PEM block) the
    gate detects it and exits non-zero. A scanner that cannot catch a planted
    secret cannot vouch for a clean tree.

The NEGATIVE proof is exercised three ways: the module self-test, the CLI
``--target`` scan path (subprocess, backend-agnostic), and the regex fallback
directly (so teeth are proven even where the ``gitleaks`` binary is absent).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import check_secret_boundary as sec

SCRIPT = Path(sec.__file__)


# --- NEGATIVE: the scanner has teeth -------------------------------------------

def test_negative_fixture_self_test_detects() -> None:
    # The gate's own negative self-check must fire on the planted fake.
    assert sec.run_negative_selftest(sec.REPO_ROOT / ".gitleaks.toml") is True


def test_regex_fallback_detects_planted_aws_and_pem(tmp_path: Path) -> None:
    # Backend-agnostic teeth: even without gitleaks, the regex fallback must catch
    # the planted AWS key AND the PEM block.
    planted = tmp_path / "planted.txt"
    planted.write_text(sec.negative_fixture_text(), encoding="utf-8")
    findings = sec.scan_with_regex(tmp_path)
    rules = {f["rule"] for f in findings}
    assert findings, "regex fallback failed to detect any planted secret (no teeth)"
    assert "private-key" in rules
    assert "aws-access-token" in rules
    # Redacted only: no raw secret material persisted in a finding.
    for f in findings:
        assert sec._NEG_AWS_SK not in f["match"]
        assert f["match"].startswith("sha256:")


def test_cli_target_scan_of_planted_exits_nonzero(tmp_path: Path) -> None:
    planted = tmp_path / "planted_fake_credential.txt"
    planted.write_text(sec.negative_fixture_text(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--target", str(planted)],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    # The planted raw secret must never appear in the gate's stdout.
    assert sec._NEG_AWS_SK not in proc.stdout


def test_planted_aws_key_is_not_the_allowlisted_example() -> None:
    # Guard the fixture itself: gitleaks (and our regex) intentionally ignore the
    # documented AKIAIOSFODNN7EXAMPLE key, so the fixture must use a distinct one.
    assert "EXAMPLE" not in sec._NEG_AWS_ID


# --- POSITIVE: clean surfaces pass ---------------------------------------------

def test_cli_target_scan_of_clean_file_exits_zero(tmp_path: Path) -> None:
    clean = tmp_path / "clean.env"
    clean.write_text(
        "API_KEY=your_api_key_here\n"
        "PASSWORD=change_me_in_production\n"
        "TOKEN=<insert-token>\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--target", str(clean)],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_regex_fallback_ignores_placeholder_values(tmp_path: Path) -> None:
    f = tmp_path / "config.py"
    f.write_text(
        'api_key = "your_binance_api_key_here"\n'
        'password = "change_me_in_production"\n'
        'secret = "${VAULT_SECRET}"\n',
        encoding="utf-8",
    )
    assert sec.scan_with_regex(tmp_path) == []


def test_env_example_is_placeholder_only() -> None:
    audit = sec.audit_env_example(sec.REPO_ROOT / ".env.example")
    assert audit["status"] in ("OK", "MISSING")
    assert audit["real_values"] == [], f"real secret in .env.example: {audit['real_values']}"


def test_allowlist_classification() -> None:
    assert sec._is_allowlisted(".github/detect-secrets.baseline")
    assert sec._is_allowlisted("docs/api/pagination.md")
    assert sec._is_allowlisted("tests/tools/test_secret_scanner.py")
    assert sec._is_allowlisted("scripts/eval/fixtures/redteam_cases.yaml")
    # Production surfaces are NOT allowlisted — full teeth land here.
    assert not sec._is_allowlisted("core/neuro/gradient_vital_signs.py")
    assert not sec._is_allowlisted("configs/prod.yaml")
    assert not sec._is_allowlisted(".env")


def test_full_gate_passes_on_clean_tree() -> None:
    # POSITIVE acceptance: the real working tree is clean → verdict PASS, exit 0.
    code, audit = sec.run_gate(write=False)
    assert audit["negative_fixture_detected"] is True
    assert audit["totals"]["high_confidence"] == 0, audit["findings"]
    assert audit["verdict"] == "PASS"
    assert code == 0
    # The committed artifact must never carry a raw secret: high-confidence findings
    # are empty, and any entry would be redacted (sha256 fingerprint) by construction.
    assert audit["findings"] == []
