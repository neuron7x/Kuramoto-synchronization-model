from __future__ import annotations

from pathlib import Path

from scripts.api_management import ApiGovernanceRunner, load_registry, validate_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_registry_loads_and_validates() -> None:
    registry_path = _repo_root() / "configs/api/registry.yaml"
    registry = load_registry(registry_path, repo_root=_repo_root())

    assert registry.routes, "expected at least one route in the registry"

    report = validate_registry(registry)
    assert report.errors == []
    assert report.warnings == []
    assert report.checks, "expected validation to record positive checks"


def test_governance_runner_generates_artifacts(tmp_path: Path) -> None:
    registry_path = _repo_root() / "configs/api/registry.yaml"
    registry = load_registry(registry_path, repo_root=_repo_root())
    runner = ApiGovernanceRunner(registry, repo_root=_repo_root())

    clients_dir = tmp_path / "clients"
    docs_dir = tmp_path / "docs"
    examples_dir = tmp_path / "examples"

    outcome = runner.orchestrate(
        clients_dir=clients_dir,
        docs_dir=docs_dir,
        examples_dir=examples_dir,
    )

    assert outcome.report.errors == []
    assert outcome.artifacts is not None

    artifacts = outcome.artifacts
    assert artifacts.python_client.exists()
    assert artifacts.typescript_client.exists()
    assert artifacts.overview.exists()
    assert artifacts.routes_index.exists()
    assert artifacts.webhooks_doc.exists()
    assert artifacts.smoke_tests_index.exists()
    assert artifacts.changelog.exists()
    assert artifacts.deprecations.exists()
    assert artifacts.migrations.exists()
    assert artifacts.visualization.exists()
    assert artifacts.examples, "expected simulator artifacts to be generated"

    routes_index = artifacts.routes_index.read_text()
    assert "get-market-signal" in routes_index
    assert "create-prediction" in routes_index

    overview_content = artifacts.overview.read_text()
    assert "TradePulse API Governance Overview" in overview_content
