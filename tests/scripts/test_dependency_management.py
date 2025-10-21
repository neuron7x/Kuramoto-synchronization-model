from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from packaging.version import Version

from scripts import cli as scripts_cli
from scripts.dependency_management import (
    DependencyRepository,
    DependencyResolutionError,
    LicensePolicy,
    LockedDependency,
    Lockfile,
    PackageMetadata,
    SemverPolicy,
    VulnerabilityRecord,
    build_compatibility_matrix,
    compare_lockfiles,
    detect_vulnerabilities,
    evaluate_license_compliance,
    find_duplicate_dependencies,
    generate_lockfile,
    generate_restore_plan,
    plan_constrained_updates,
    prune_lockfile,
    render_dependency_graph,
)


@pytest.fixture
def sample_metadata() -> list[PackageMetadata]:
    return [
        PackageMetadata(
            name="alpha",
            version=Version("1.0.0"),
            dependencies=("bravo>=1.0,<2.0", "charlie==1.0.0"),
            licenses=("MIT",),
            python_versions=("3.10", "3.11"),
            mirror_url="https://mirror.example/simple/alpha",
        ),
        PackageMetadata(
            name="alpha",
            version=Version("1.0.1"),
            dependencies=("bravo>=1.0,<2.0", "charlie==1.0.0"),
            licenses=("MIT",),
            python_versions=("3.11", "3.12"),
            mirror_url="https://mirror.example/simple/alpha",
        ),
        PackageMetadata(
            name="alpha",
            version=Version("1.1.0"),
            dependencies=("bravo>=1.0,<2.0", "charlie==1.0.0"),
            licenses=("MIT",),
            python_versions=("3.11", "3.12"),
        ),
        PackageMetadata(
            name="alpha",
            version=Version("2.0.0"),
            dependencies=("bravo>=1.0,<3.0",),
            licenses=("MIT",),
            python_versions=("3.12",),
        ),
        PackageMetadata(
            name="bravo",
            version=Version("1.0.0"),
            dependencies=("delta==1.0.0",),
            licenses=("Apache-2.0",),
            python_versions=("3.10", "3.11"),
            vulnerabilities=(
                VulnerabilityRecord(
                    identifier="CVE-2024-0001",
                    severity="high",
                    fix_versions=("1.0.1",),
                    aliases=("GHSA-1111",),
                    description="Example advisory",
                ),
            ),
        ),
        PackageMetadata(
            name="bravo",
            version=Version("1.0.1"),
            dependencies=("delta==1.0.0",),
            licenses=("Apache-2.0",),
            python_versions=("3.11", "3.12"),
        ),
        PackageMetadata(
            name="charlie",
            version=Version("1.0.0"),
            dependencies=(),
            licenses=("BSD-3-Clause",),
            python_versions=("3.10", "3.11", "3.12"),
        ),
        PackageMetadata(
            name="delta",
            version=Version("1.0.0"),
            dependencies=(),
            licenses=("GPL-3.0",),
            python_versions=("3.11",),
        ),
        PackageMetadata(
            name="echo",
            version=Version("1.0.0"),
            dependencies=(),
            licenses=("MIT",),
            python_versions=("3.11",),
        ),
    ]


@pytest.fixture
def repository(sample_metadata: list[PackageMetadata]) -> DependencyRepository:
    return DependencyRepository(sample_metadata)


def test_generate_lockfile_resolves_transitive_dependencies(repository: DependencyRepository) -> None:
    lock = generate_lockfile(["alpha>=1.0,<2.0"], repository)
    names = {package.canonical_name for package in lock.packages}
    assert names == {"alpha", "bravo", "charlie", "delta"}
    assert lock.get("alpha").version == Version("1.1.0")


def test_duplicate_detection_identifies_conflicts() -> None:
    lock = Lockfile(
        generated_at=datetime.now(timezone.utc),
        packages=(
            LockedDependency(name="alpha", version=Version("1.0.0")),
            LockedDependency(name="Alpha", version=Version("1.0.1")),
        ),
    )
    duplicates = find_duplicate_dependencies(lock)
    assert duplicates == ("Alpha",)


def test_update_planning_respects_semver_policy(repository: DependencyRepository) -> None:
    lock = Lockfile(
        generated_at=datetime.now(timezone.utc),
        packages=(
            LockedDependency(name="alpha", version=Version("1.0.0")),
        ),
    )
    plans_patch = plan_constrained_updates(lock, repository, policy=SemverPolicy())
    assert plans_patch and plans_patch[0].target_version == Version("1.0.1")

    plans_minor = plan_constrained_updates(lock, repository, policy=SemverPolicy(allow_minor=True))
    assert any(plan.target_version == Version("1.1.0") for plan in plans_minor)

    plans_major = plan_constrained_updates(lock, repository, policy=SemverPolicy(allow_major=True, allow_minor=True))
    assert any(plan.target_version == Version("2.0.0") for plan in plans_major)


def test_graph_rendering_contains_edges(repository: DependencyRepository) -> None:
    lock = generate_lockfile(["alpha>=1.0,<2.0"], repository)
    dot = render_dependency_graph(lock)
    assert "alpha" in dot and "->" in dot


def test_vulnerability_detection_flags_insecure_versions(repository: DependencyRepository) -> None:
    lock = Lockfile(
        generated_at=datetime.now(timezone.utc),
        packages=(
            LockedDependency(name="bravo", version=Version("1.0.0")),
        ),
    )
    findings = detect_vulnerabilities(lock, repository)
    assert findings and findings[0].advisory.identifier == "CVE-2024-0001"


def test_license_compliance_enforces_policy(repository: DependencyRepository) -> None:
    lock = Lockfile(
        generated_at=datetime.now(timezone.utc),
        packages=(
            LockedDependency(name="delta", version=Version("1.0.0")),
        ),
    )
    policy = LicensePolicy.from_dict({"allowed": ["MIT"], "restricted": [], "forbidden": ["GPL-3.0"]})
    issues = evaluate_license_compliance(lock, repository, policy)
    assert issues and issues[0].classification == "forbidden"


def test_prune_lockfile_removes_unused_packages(repository: DependencyRepository) -> None:
    lock = generate_lockfile(["alpha>=1.0,<2.0"], repository)
    pruned = prune_lockfile(lock, ["charlie"])
    assert {pkg.canonical_name for pkg in pruned.packages} == {"charlie"}


def test_repository_cache_roundtrip(tmp_path: Path, sample_metadata: list[PackageMetadata]) -> None:
    cache_path = tmp_path / "repo-cache.json"
    repo = DependencyRepository(sample_metadata, cache_path=cache_path)
    assert cache_path.exists()

    offline_repo = DependencyRepository(cache_path=cache_path, offline=True)
    versions = offline_repo.available_versions("alpha")
    assert versions[-1] == Version("2.0.0")


def test_offline_missing_package_raises(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    repo = DependencyRepository(cache_path=cache_path, offline=True)
    with pytest.raises(DependencyResolutionError):
        repo.available_versions("missing")


def test_mirror_configuration(repository: DependencyRepository) -> None:
    assert repository.mirror_for("alpha") == "https://mirror.example/simple/alpha"


def test_restore_plan_outputs_commands(repository: DependencyRepository) -> None:
    lock = generate_lockfile(["alpha>=1.0,<2.0"], repository)
    commands = generate_restore_plan(lock, python_executable="python3")
    assert commands[0].startswith("python3 -m pip install")


def test_compatibility_matrix_reports_support(repository: DependencyRepository) -> None:
    lock = generate_lockfile(["alpha>=1.0,<2.0"], repository)
    matrix = build_compatibility_matrix(lock, repository, ["3.10", "3.12"])
    assert matrix["alpha"]["3.12"] is True
    assert matrix["delta"]["3.10"] is False


def test_compare_lockfiles_reports_changes(repository: DependencyRepository) -> None:
    lock_old = Lockfile(
        generated_at=datetime.now(timezone.utc),
        packages=(
            LockedDependency(name="alpha", version=Version("1.0.0")),
            LockedDependency(name="bravo", version=Version("1.0.0")),
        ),
    )
    lock_new = Lockfile(
        generated_at=datetime.now(timezone.utc),
        packages=(
            LockedDependency(name="alpha", version=Version("1.0.1")),
            LockedDependency(name="charlie", version=Version("1.0.0")),
        ),
    )
    report = compare_lockfiles(lock_old, lock_new)
    assert any(entry.name == "alpha" for entry in report.updated)
    assert any(entry.name == "bravo" for entry in report.removed)
    assert any(entry.name == "charlie" for entry in report.added)


def test_cli_lock_command_creates_lockfile(tmp_path: Path, sample_metadata: list[PackageMetadata]) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_payload = {
        "packages": [entry.to_dict() for entry in sample_metadata],
    }
    metadata_path.write_text(json.dumps(metadata_payload, indent=2), encoding="utf-8")

    requirements = tmp_path / "requirements.txt"
    requirements.write_text("alpha>=1.0,<2.0\n", encoding="utf-8")
    output = tmp_path / "lock.json"

    argv = [
        "dependencies",
        "--metadata",
        str(metadata_path),
        "lock",
        "--requirements",
        str(requirements),
        "--output",
        str(output),
    ]
    exit_code = scripts_cli.main(argv)
    assert exit_code == 0
    assert output.exists()

