# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import supply_chain


def test_load_dependencies_parses_and_sorts(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.lock"
    requirements.write_text("B==1.0\na==2.0\n", encoding="utf-8")

    dependencies = supply_chain.load_dependencies([requirements])

    assert [dep.name for dep in dependencies] == ["a", "B"]
    assert all(dep.is_pinned for dep in dependencies)


def test_load_dependencies_missing_file(tmp_path: Path) -> None:
    with pytest.raises(supply_chain.DependencyError):
        supply_chain.load_dependencies([tmp_path / "missing.lock"])


def test_dependency_component_includes_metadata(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.lock"
    requirements.write_text("demo[extra]==1.0; python_version>='3.9'", encoding="utf-8")
    dependency = supply_chain.load_dependencies([requirements])[0]

    component = dependency.to_component()
    assert component["name"] == "demo"
    assert component["version"] == "1.0"

    properties = {prop["name"]: prop["value"] for prop in component["properties"]}
    assert properties["dependency.source"].endswith("requirements.lock")
    assert properties["python.extras"] == "extra"
    assert "python.marker" in properties


def test_verify_dependencies_reports_unpinned_and_denylisted(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.lock"
    requirements.write_text("ctx>=1.0\n", encoding="utf-8")
    dependency = supply_chain.load_dependencies([requirements])[0]

    denylist = [
        supply_chain.DenylistEntry(
            name="ctx",
            specifier=None,
            reason="Known malicious package.",
            references=("https://example.com/ctx",),
            cves=(),
        )
    ]

    report = supply_chain.verify_dependencies([dependency], denylist, require_pins=True)

    assert report.has_failures()
    reasons = [issue.message for issue in report.issues]
    assert any("not pinned" in reason for reason in reasons)
    assert any("Known malicious" in reason for reason in reasons)


def test_build_cyclonedx_sbom_structure(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.lock"
    requirements.write_text("alpha==1.0\n", encoding="utf-8")
    dependency = supply_chain.load_dependencies([requirements])[0]

    sbom = supply_chain.build_cyclonedx_sbom(
        [dependency],
        component_name="GeoSync",
        component_version="1.2.3",
    )

    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["metadata"]["component"]["name"] == "GeoSync"
    assert sbom["components"][0]["name"] == "alpha"


def test_write_verification_report(tmp_path: Path) -> None:
    dependency = supply_chain.Dependency(
        name="alpha",
        raw_requirement="alpha==1.0",
        source=Path("requirements.lock"),
        requirement=supply_chain.Requirement("alpha==1.0"),
    )
    report = supply_chain.DependencyVerificationReport(
        generated_at=supply_chain.datetime.now(supply_chain.timezone.utc),
        dependencies=(dependency,),
        issues=(),
    )
    destination = tmp_path / "report.json"

    supply_chain.write_verification_report(report, destination)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["dependency_count"] == 1
