# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from packaging.requirements import Requirement

from scripts import supply_chain


def _dependency(name: str, requirement: str) -> supply_chain.Dependency:
    return supply_chain.Dependency(
        name=name,
        raw_requirement=requirement,
        source=Path("requirements.lock"),
        requirement=Requirement(requirement),
    )


def test_load_allowlist_parses_entries(tmp_path: Path) -> None:
    data = {
        "packages": [
            {
                "name": "demo",
                "allow_unpinned": True,
                "allow_multiple_versions": False,
                "specifier": ">=1.0,<2.0",
                "reason": "Needed for beta testing",
            }
        ]
    }
    path = tmp_path / "allowlist.yaml"
    path.write_text(json.dumps(data), encoding="utf-8")

    entries = supply_chain.load_allowlist(path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.canonical_name == "demo"
    assert entry.allow_unpinned is True
    assert entry.allow_multiple_versions is False
    assert entry.specifier is not None
    assert entry.specifier.contains("1.5")


def test_verify_dependencies_respects_allowlist() -> None:
    dep_a = _dependency("alpha", "alpha==1.0.0")
    dep_b = _dependency("alpha", "alpha==1.2.0")
    dep_unpinned = _dependency("beta", "beta>=1.0")

    denylist: list[supply_chain.DenylistEntry] = []
    allowlist = [
        supply_chain.AllowlistEntry(
            name="alpha",
            specifier=None,
            allow_unpinned=False,
            allow_multiple_versions=True,
            reason=None,
        ),
        supply_chain.AllowlistEntry(
            name="beta",
            specifier=None,
            allow_unpinned=True,
            allow_multiple_versions=False,
            reason="Upstream release cadence unstable",
        ),
    ]

    report = supply_chain.verify_dependencies(
        [dep_a, dep_b, dep_unpinned],
        denylist,
        allowlist=allowlist,
        require_pins=True,
    )
    assert not report.issues


def test_load_license_policy_and_normalisation(tmp_path: Path) -> None:
    payload = {
        "allowed": ["MIT"],
        "restricted": ["GPL-3.0"],
        "forbidden": ["AGPL-3.0"],
        "aliases": {"MIT License": "MIT"},
        "exceptions": [
            {
                "package": "demo",
                "license": "GPL-3.0",
                "reason": "Contractual waiver",
                "expires": "2099-01-01",
            }
        ],
    }
    policy_path = tmp_path / "license_policy.yaml"
    policy_path.write_text(json.dumps(payload), encoding="utf-8")

    policy = supply_chain.load_license_policy(policy_path)
    key, value = policy.normalise("MIT License")
    assert key and value == "MIT"
    assert policy.exceptions


def test_evaluate_license_compliance_classifies(tmp_path: Path) -> None:
    dependencies = [
        _dependency("lib-ok", "lib-ok==1.0"),
        _dependency("lib-restricted", "lib-restricted==2.0"),
        _dependency("lib-forbidden", "lib-forbidden==3.0"),
        _dependency("lib-exception", "lib-exception==4.0"),
    ]
    sbom = {
        "components": [
            {
                "name": "lib-ok",
                "version": "1.0",
                "licenses": [{"license": {"id": "MIT"}}],
            },
            {
                "name": "lib-restricted",
                "version": "2.0",
                "licenses": [{"license": {"id": "GPL-3.0"}}],
            },
            {
                "name": "lib-forbidden",
                "version": "3.0",
                "licenses": [{"license": {"id": "AGPL-3.0"}}],
            },
            {
                "name": "lib-exception",
                "version": "4.0",
                "licenses": [{"license": {"id": "GPL-3.0"}}],
            },
        ]
    }

    policy_payload = {
        "allowed": ["MIT"],
        "restricted": ["GPL-3.0"],
        "forbidden": ["AGPL-3.0"],
        "aliases": {},
        "exceptions": [
            {
                "package": "lib-exception",
                "license": "GPL-3.0",
                "reason": "Risk accepted",
                "expires": "2099-01-01",
            }
        ],
    }
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(json.dumps(policy_payload), encoding="utf-8")
    policy = supply_chain.load_license_policy(policy_path)

    issues = supply_chain.evaluate_license_compliance(
        dependencies, sbom, policy, now=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )

    classifications = {issue.dependency.canonical_name: issue.classification for issue in issues}
    assert "lib-ok" not in classifications
    assert classifications["lib-restricted"] == "restricted"
    assert classifications["lib-forbidden"] == "forbidden"
    assert classifications["lib-exception"] == "exception"


def test_load_vulnerability_report_supports_formats(tmp_path: Path) -> None:
    aggregated = tmp_path / "aggregated.json"
    aggregated.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "name": "demo",
                        "version": "1.0",
                        "advisory": "CVE-2024-0001",
                        "severity": "HIGH",
                        "fix_versions": ["1.1"],
                        "aliases": ["GHSA-1234"],
                        "description": "Example advisory",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    findings = supply_chain.load_vulnerability_report(aggregated)
    assert len(findings) == 1
    assert findings[0].severity == "high"

    raw = tmp_path / "raw.json"
    raw.write_text(
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "demo",
                        "version": "1.0",
                        "vulns": [
                            {
                                "id": "CVE-2024-9999",
                                "severity": "critical",
                                "fix_versions": ["2.0"],
                                "aliases": [],
                                "description": "Another advisory",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    findings = supply_chain.load_vulnerability_report(raw)
    assert len(findings) == 1
    assert findings[0].advisory == "CVE-2024-9999"


def test_build_compliance_report_to_dict() -> None:
    dependency = _dependency("pkg", "pkg==1.0")
    verification = supply_chain.DependencyVerificationReport(
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        dependencies=(dependency,),
        issues=(
            supply_chain.VerificationIssue(
                dependency=dependency,
                message="example",
                severity=supply_chain.Severity.WARNING,
            ),
        ),
    )
    license_issue = supply_chain.LicenseIssue(
        dependency=dependency,
        licenses=("MIT",),
        severity=supply_chain.Severity.WARNING,
        classification="restricted",
        message="Review",
    )
    vulnerability = supply_chain.VulnerabilityFinding(
        name="pkg",
        version="1.0",
        advisory="CVE-2024-42",
        severity="medium",
        fix_versions=("1.1",),
        aliases=("GHSA-demo",),
        description="Test",
    )

    report = supply_chain.build_compliance_report(
        verification,
        [license_issue],
        [vulnerability],
    )
    payload = report.to_dict()
    assert payload["license_compliance"]["issue_count"] == 1
    assert payload["vulnerabilities"]["total"] == 1
    assert payload["summary"]["dependency_issues"] == 1
