# SPDX-License-Identifier: MIT
"""Enforce redaction of historical security scanner payloads.

The archived scanner report is retained only for finding metadata and SHA-bound
forensic fingerprints, never for credential material. This does not establish
that historic exposed credentials have been revoked or Git history purged.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "archive_snapshots/github_9e6e4792_unique/audit/artifacts/gitleaks.json"
MARKER = "[REDACTED: original historical finding; see Fingerprint, File, Commit, RuleID]"


def test_archived_security_report_keeps_143_findings_without_secret_values() -> None:
    assert REPORT.is_file(), "archived security incident report must not vanish"
    findings = json.loads(REPORT.read_text(encoding="utf-8"))
    assert len(findings) == 143
    assert all(isinstance(x["Fingerprint"], str) and x["Fingerprint"] for x in findings)
    assert all(x["Match"] == MARKER and x["Secret"] == MARKER for x in findings)
    # A leaked historical PEM header must not re-enter the committed report.
    pem_header = "-----BEGIN " + "PRIVATE KEY-----"
    assert pem_header not in REPORT.read_text(encoding="utf-8")


def test_redaction_marker_cannot_be_accepted_as_secret_proof() -> None:
    """Redacted receipt protects secrets; it cannot certify revocation."""
    assert "original historical finding" in MARKER
    assert "revoked" not in MARKER.lower()
    assert "rotated" not in MARKER.lower()
