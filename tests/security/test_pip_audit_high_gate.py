# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for the fail-closed pip-audit HIGH/CRITICAL gate.

These tests lock in the fix for the *vacuous gate* defect: ``pip-audit``'s JSON
report carries no per-vulnerability ``severity`` field, so the previous gate —
which read ``vuln["severity"]`` — counted zero HIGH/CRITICAL findings for every
input and could never fail. The gate now derives severity from the CVSS vector
and fails closed. The most important assertion here is
``test_high_finding_blocks``: it would have *passed silently* against the broken
implementation.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "pip_audit_high_gate",
    _ROOT / ".github" / "scripts" / "pip_audit_high_gate.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_gate = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _gate
_SPEC.loader.exec_module(_gate)

_TODAY = date(2026, 6, 21)


def _report(name: str, version: str, vuln_id: str, aliases: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "dependencies": [
            {
                "name": name,
                "version": version,
                "vulns": [{"id": vuln_id, "aliases": list(aliases)}],
            }
        ]
    }


# ---------------------------------------------------------------------------
# CVSS base-score computation — verified against published NVD base scores.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("vector", "expected"),
    [
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0),  # Log4Shell
        ("CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8),  # network RCE
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N", 7.5),  # high-confidentiality
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1),  # reflected XSS
        ("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:L", 5.3),  # torch CVE-2025-3000
        ("CVSS:3.1/AV:N/AC:H/PR:H/UI:R/S:U/C:N/I:N/A:L", 2.0),  # low
    ],
)
def test_cvss3_base_score_matches_nvd(vector: str, expected: float) -> None:
    assert _gate.cvss3_base_score(vector) == expected


def test_cvss3_base_score_rejects_garbage() -> None:
    assert _gate.cvss3_base_score("not-a-vector") is None
    assert _gate.cvss3_base_score("CVSS:3.1/AV:N") is None


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (10.0, "CRITICAL"),
        (9.0, "CRITICAL"),
        (7.0, "HIGH"),
        (4.0, "MEDIUM"),
        (0.1, "LOW"),
        (0.0, "NONE"),
    ],
)
def test_classify_bands(score: float, band: str) -> None:
    assert _gate.classify(score) == band


# ---------------------------------------------------------------------------
# OSV record → severity.
# ---------------------------------------------------------------------------
def test_severity_prefers_cvss_v3_vector() -> None:
    record = {
        "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"}]
    }
    assert _gate._severity_from_osv_record(record) == "CRITICAL"


def test_severity_falls_back_to_text() -> None:
    record = {"database_specific": {"severity": "MODERATE"}}
    assert _gate._severity_from_osv_record(record) == "MEDIUM"


def test_severity_unknown_when_unrated() -> None:
    assert _gate._severity_from_osv_record({}) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Gate evaluation — the core fail-closed contract.
# ---------------------------------------------------------------------------
def _resolver(table: dict[str, str]) -> _gate.SeverityResolver:
    def resolve(advisory_id: str, aliases: list[str]) -> str:
        for key in (advisory_id, *aliases):
            if key in table:
                return table[key]
        return "UNKNOWN"

    return resolve


def test_high_finding_blocks() -> None:
    """The keystone regression: a HIGH advisory MUST fail the gate.

    Against the previous (vacuous) implementation this finding produced exit 0.
    """
    findings = _gate.evaluate(
        [_report("acme", "1.0.0", "CVE-2099-0001")],
        resolver=_resolver({"CVE-2099-0001": "HIGH"}),
        active_exceptions=set(),
    )
    assert len(_gate.blocking_findings(findings)) == 1


def test_critical_finding_blocks() -> None:
    findings = _gate.evaluate(
        [_report("acme", "1.0.0", "CVE-2099-0002")],
        resolver=_resolver({"CVE-2099-0002": "CRITICAL"}),
        active_exceptions=set(),
    )
    assert len(_gate.blocking_findings(findings)) == 1


def test_medium_finding_passes() -> None:
    findings = _gate.evaluate(
        [_report("torch", "2.11.0", "GHSA-rrmf-rvhw-rf47")],
        resolver=_resolver({"GHSA-rrmf-rvhw-rf47": "MEDIUM"}),
        active_exceptions=set(),
    )
    assert _gate.blocking_findings(findings) == []


def test_unknown_severity_fails_closed() -> None:
    findings = _gate.evaluate(
        [_report("acme", "1.0.0", "CVE-2099-0003")],
        resolver=_resolver({}),  # resolver returns UNKNOWN
        active_exceptions=set(),
    )
    assert findings[0].severity == "CRITICAL"
    assert len(_gate.blocking_findings(findings)) == 1


def test_active_exception_allows_high_finding() -> None:
    findings = _gate.evaluate(
        [_report("acme", "1.0.0", "CVE-2099-0004", aliases=("GHSA-aaaa-bbbb-cccc",))],
        resolver=_resolver({"CVE-2099-0004": "HIGH"}),
        active_exceptions={"GHSA-aaaa-bbbb-cccc"},
    )
    assert _gate.blocking_findings(findings) == []
    assert findings[0].excepted is True


def test_empty_report_passes() -> None:
    findings = _gate.evaluate(
        [{"dependencies": []}], resolver=_resolver({}), active_exceptions=set()
    )
    assert _gate.blocking_findings(findings) == []


def test_duplicate_findings_collapsed() -> None:
    report = _report("acme", "1.0.0", "CVE-2099-0005")
    findings = _gate.evaluate(
        [report, report],
        resolver=_resolver({"CVE-2099-0005": "HIGH"}),
        active_exceptions=set(),
    )
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# Ledger parsing.
# ---------------------------------------------------------------------------
_LEDGER_TEMPLATE = """# Ledger

<!-- LEDGER-DATA -->
```json
{{
  "schema_version": 1,
  "exceptions": [
    {{
      "package": "torch",
      "advisory_id": "CVE-2025-32434",
      "expiry_date": "{expiry}"
    }}
  ]
}}
```
"""


def test_ledger_active_entry_parsed(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(_LEDGER_TEMPLATE.format(expiry="2099-01-01"), encoding="utf-8")
    assert _gate.load_active_exceptions(ledger, today=_TODAY) == {"CVE-2025-32434"}


def test_ledger_expired_entry_ignored(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(_LEDGER_TEMPLATE.format(expiry="2020-01-01"), encoding="utf-8")
    assert _gate.load_active_exceptions(ledger, today=_TODAY) == set()


def test_ledger_absent_is_empty(tmp_path: Path) -> None:
    assert _gate.load_active_exceptions(tmp_path / "nope.md", today=_TODAY) == set()


# ---------------------------------------------------------------------------
# CLI exit codes.
# ---------------------------------------------------------------------------
def test_main_blocks_high(tmp_path: Path) -> None:
    report = tmp_path / "audit.json"
    import json

    report.write_text(json.dumps(_report("acme", "1.0.0", "CVE-2099-0006")), encoding="utf-8")
    rc = _gate.main(
        [str(report)],
        resolver=_resolver({"CVE-2099-0006": "HIGH"}),
        ledger_path=tmp_path / "absent.md",
        today=_TODAY,
    )
    assert rc == 1


def test_main_passes_clean(tmp_path: Path) -> None:
    report = tmp_path / "audit.json"
    import json

    report.write_text(json.dumps({"dependencies": []}), encoding="utf-8")
    rc = _gate.main(
        [str(report)],
        resolver=_resolver({}),
        ledger_path=tmp_path / "absent.md",
        today=_TODAY,
    )
    assert rc == 0
