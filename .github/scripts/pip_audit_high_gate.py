#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed HIGH/CRITICAL dependency-vulnerability gate over pip-audit JSON.

Why this exists
---------------
``pip-audit``'s JSON report does **not** carry a per-vulnerability severity:
each ``dependencies[].vulns[]`` entry has only ``id``, ``aliases``,
``fix_versions`` and ``description``. The previous implementation read
``vuln["severity"]`` and therefore counted **zero** HIGH/CRITICAL findings for
*every possible input* — a fail-open gate that printed "passed" even when
pip-audit reported CRITICAL CVEs.

This version resolves each advisory's severity from the OSV database (the same
source pip-audit queries) by computing the CVSS base score from the published
vector, and **fails closed**:

* a finding classified HIGH or CRITICAL fails the gate, unless its advisory id
  (or one of its aliases) carries an *active*, non-expired entry in the
  vulnerability exception ledger
  (``docs/security/vulnerability_exception_ledger.md``);
* a finding whose severity cannot be established (no parseable CVSS vector and
  no textual severity from OSV) is treated as **CRITICAL** — unknown risk is
  blocking, never silently ignored.

The severity resolver and the ledger reader are injectable so the behaviour is
unit-testable offline (see ``tests/security/test_pip_audit_high_gate.py``); the
default resolver queries OSV over the network, which the surrounding
``security-deep.yml`` job already does for pip-audit itself.

Exit codes::

    0  no blocking (HIGH/CRITICAL, un-excepted) findings
    1  one or more blocking findings
    2  malformed invocation (unreadable report / ledger / schema drift)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LEDGER = _ROOT / "docs" / "security" / "vulnerability_exception_ledger.md"
_LEDGER_MARKER = "LEDGER-DATA"
_OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"

# CVSS base-score band → label (CVSS v3.x qualitative severity rating scale).
_CRITICAL_FLOOR = 9.0
_HIGH_FLOOR = 7.0
_MEDIUM_FLOOR = 4.0
_LOW_FLOOR = 0.1

#: Severity that blocks the gate.
_BLOCKING = frozenset({"HIGH", "CRITICAL"})

#: Textual OSV/GHSA severities mapped onto the CVSS qualitative scale.
_TEXT_SEVERITY = {
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MODERATE": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


# ---------------------------------------------------------------------------
# CVSS v3.x base-score computation (spec: FIRST CVSS v3.1, §7.1).
# ---------------------------------------------------------------------------
_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_AC = {"L": 0.77, "H": 0.44}
_UI = {"N": 0.85, "R": 0.62}
_PR_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}
_CIA = {"H": 0.56, "L": 0.22, "N": 0.0}


def _roundup(value: float) -> float:
    """CVSS v3.1 ``Roundup`` — round to one decimal, always upward."""
    scaled = round(value * 100_000)
    if scaled % 10_000 == 0:
        return scaled / 100_000.0
    return (math.floor(scaled / 10_000) + 1) / 10.0


def cvss3_base_score(vector: str) -> float | None:
    """Compute the CVSS v3.x base score from a vector string.

    Returns ``None`` if the vector is not a parseable CVSS v3 base vector.
    """
    metrics: dict[str, str] = {}
    body = vector.strip()
    if body.upper().startswith("CVSS:3"):
        body = body.split("/", 1)[1] if "/" in body else ""
    for part in body.split("/"):
        if ":" in part:
            key, val = part.split(":", 1)
            metrics[key.upper()] = val.upper()

    try:
        av = _AV[metrics["AV"]]
        ac = _AC[metrics["AC"]]
        ui = _UI[metrics["UI"]]
        scope_changed = metrics["S"] == "C"
        pr = (_PR_CHANGED if scope_changed else _PR_UNCHANGED)[metrics["PR"]]
        conf = _CIA[metrics["C"]]
        integ = _CIA[metrics["I"]]
        avail = _CIA[metrics["A"]]
    except KeyError:
        return None

    iss = 1.0 - (1.0 - conf) * (1.0 - integ) * (1.0 - avail)
    if scope_changed:
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    else:
        impact = 6.42 * iss
    exploitability = 8.22 * av * ac * pr * ui

    if impact <= 0:
        return 0.0
    raw = (impact + exploitability) * (1.08 if scope_changed else 1.0)
    return _roundup(min(raw, 10.0))


def classify(score: float) -> str:
    """Map a CVSS base score onto its qualitative band."""
    if score >= _CRITICAL_FLOOR:
        return "CRITICAL"
    if score >= _HIGH_FLOOR:
        return "HIGH"
    if score >= _MEDIUM_FLOOR:
        return "MEDIUM"
    if score >= _LOW_FLOOR:
        return "LOW"
    return "NONE"


# ---------------------------------------------------------------------------
# Severity resolution.
# ---------------------------------------------------------------------------
SeverityResolver = Callable[[str, Sequence[str]], str]


def _severity_from_osv_record(record: dict[str, Any]) -> str:
    """Derive the qualitative severity from an OSV vulnerability record.

    Prefers the highest CVSS v3.x base score across published vectors; falls
    back to a textual ``database_specific.severity``. Returns ``"UNKNOWN"`` if
    neither is available so the caller can fail closed.
    """
    best: float | None = None
    for entry in record.get("severity", []) or []:
        if str(entry.get("type", "")).upper().startswith("CVSS_V3"):
            score = cvss3_base_score(str(entry.get("score", "")))
            if score is not None and (best is None or score > best):
                best = score
    if best is not None:
        return classify(best)

    text = str(record.get("database_specific", {}).get("severity", "")).upper()
    return _TEXT_SEVERITY.get(text, "UNKNOWN")


def _osv_resolver(advisory_id: str, aliases: Sequence[str]) -> str:
    """Default resolver: query OSV for ``advisory_id`` (then its aliases)."""
    for candidate in (advisory_id, *aliases):
        if not candidate:
            continue
        url = _OSV_VULN_URL.format(id=urllib.parse.quote(candidate))
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                record = json.load(resp)
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError):
            continue
        severity = _severity_from_osv_record(record)
        if severity != "UNKNOWN":
            return severity
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Vulnerability exception ledger.
# ---------------------------------------------------------------------------
def load_active_exceptions(
    ledger_path: Path,
    *,
    today: date,
) -> set[str]:
    """Return the set of advisory ids with an active (non-expired) exception.

    A malformed or absent ledger yields an empty set: the gate then treats
    every HIGH/CRITICAL finding as blocking (fail closed).
    """
    try:
        text = ledger_path.read_text(encoding="utf-8")
    except OSError:
        return set()

    marker = text.find(_LEDGER_MARKER)
    if marker == -1:
        return set()
    fence = text.find("```json", marker)
    if fence == -1:
        return set()
    start = text.find("\n", fence) + 1
    end = text.find("```", start)
    if end == -1:
        return set()

    try:
        data = json.loads(text[start:end])
    except ValueError:
        return set()

    active: set[str] = set()
    for entry in data.get("exceptions", []) or []:
        advisory = str(entry.get("advisory_id", "")).strip()
        expiry_raw = str(entry.get("expiry_date", "")).strip()
        if not advisory or not expiry_raw:
            continue
        try:
            expiry = date.fromisoformat(expiry_raw)
        except ValueError:
            continue
        if expiry >= today:
            active.add(advisory)
    return active


# ---------------------------------------------------------------------------
# Gate evaluation.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Finding:
    package: str
    version: str
    advisory_id: str
    aliases: tuple[str, ...]
    severity: str
    excepted: bool

    def __str__(self) -> str:
        flag = " (excepted)" if self.excepted else ""
        return f"{self.severity} {self.package}=={self.version} {self.advisory_id}{flag}"


def _iter_vulns(report: dict[str, Any]) -> Iterable[tuple[str, str, str, tuple[str, ...]]]:
    for dep in report.get("dependencies", []) or []:
        name = str(dep.get("name", "")).strip() or "<unknown>"
        version = str(dep.get("version", "")).strip() or "<unknown>"
        for vuln in dep.get("vulns", []) or []:
            advisory = str(vuln.get("id", "")).strip()
            aliases = tuple(str(a).strip() for a in (vuln.get("aliases") or []) if str(a).strip())
            yield name, version, advisory, aliases


def evaluate(
    reports: Sequence[dict[str, Any]],
    *,
    resolver: SeverityResolver,
    active_exceptions: set[str],
) -> list[Finding]:
    """Resolve severity for every reported vuln and return all findings."""
    findings: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()
    for report in reports:
        for name, version, advisory, aliases in _iter_vulns(report):
            key = (name, version, advisory)
            if key in seen:
                continue
            seen.add(key)
            severity = resolver(advisory, aliases)
            if severity == "UNKNOWN":
                # Fail closed: an advisory we cannot rate is treated as the
                # worst case until a human rates and (if warranted) excepts it.
                severity = "CRITICAL"
            excepted = bool({advisory, *aliases} & active_exceptions)
            findings.append(Finding(name, version, advisory, aliases, severity, excepted))
    return findings


def blocking_findings(findings: Sequence[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity in _BLOCKING and not f.excepted]


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
def _load_reports(paths: Sequence[str]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in paths:
        try:
            reports.append(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"pip-audit report unreadable ({path}): {exc}") from exc
    return reports


def main(
    argv: Sequence[str] | None = None,
    *,
    resolver: SeverityResolver = _osv_resolver,
    ledger_path: Path = _DEFAULT_LEDGER,
    today: date | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", help="pip-audit JSON report paths")
    args = parser.parse_args(argv)

    reports = _load_reports(args.reports)
    active = load_active_exceptions(ledger_path, today=today or date.today())
    findings = evaluate(reports, resolver=resolver, active_exceptions=active)
    blocking = blocking_findings(findings)

    for finding in findings:
        if finding.severity in _BLOCKING:
            print(("BLOCK " if not finding.excepted else "ALLOW ") + str(finding))

    if blocking:
        print(
            f"pip-audit gate FAILED: {len(blocking)} un-excepted HIGH/CRITICAL finding(s).",
            file=sys.stderr,
        )
        return 1

    excepted = sum(1 for f in findings if f.excepted and f.severity in _BLOCKING)
    print(
        "pip-audit HIGH/CRITICAL gate passed "
        f"({len(findings)} advisory finding(s) rated; {excepted} ledgered)."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
