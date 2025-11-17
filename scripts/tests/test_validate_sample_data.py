from __future__ import annotations

import hashlib
from pathlib import Path

from scripts import validate_sample_data


def _write_contract(
    path: Path,
    *,
    artifact_path: str,
    checksum: str,
    size_bytes: int | None = None,
) -> None:
    front_matter_lines = [
        "---",
        "owner: data@tradepulse",
        "review_cadence: quarterly",
        "artifacts:",
        "  - path: " + artifact_path,
        "    checksum: " + checksum,
    ]
    if size_bytes is not None:
        front_matter_lines.append(f"    size_bytes: {size_bytes}")
    front_matter_lines.append("---\n")
    path.write_text("\n".join(front_matter_lines) + "# Contract\n", encoding="utf-8")


def test_validate_contract_happy_path(tmp_path: Path) -> None:
    repo_root = tmp_path
    data_dir = repo_root / "data"
    data_dir.mkdir()
    artifact = data_dir / "sample.csv"
    artifact.write_text("x,y\n1,2\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    contract_dir = repo_root / "docs" / "data"
    contract_dir.mkdir(parents=True)
    contract = contract_dir / "sample.md"
    _write_contract(
        contract,
        artifact_path="data/sample.csv",
        checksum=f"sha256:{digest}",
        size_bytes=artifact.stat().st_size,
    )

    report = validate_sample_data.validate_contract(contract, repo_root=repo_root)

    assert report.valid()
    assert report.artifacts[0].valid
    assert report.artifacts[0].actual_checksum == digest


def test_validate_contract_relative_to_contract_directory(tmp_path: Path) -> None:
    repo_root = tmp_path
    contract_dir = repo_root / "docs" / "datasets" / "beta"
    contract_dir.mkdir(parents=True)
    artifact = contract_dir / "local.csv"
    artifact.write_bytes(b"alpha\n")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    contract = contract_dir / "beta.md"
    _write_contract(
        contract,
        artifact_path="local.csv",
        checksum=digest,
    )

    report = validate_sample_data.validate_contract(contract, repo_root=repo_root)

    assert report.valid()
    assert report.artifacts[0].resolved_path == artifact.resolve()


def test_validate_contract_detects_checksum_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path
    data_dir = repo_root / "data"
    data_dir.mkdir()
    artifact = data_dir / "bad.csv"
    artifact.write_text("a\n", encoding="utf-8")

    contract_dir = repo_root / "docs" / "data"
    contract_dir.mkdir(parents=True)
    contract = contract_dir / "bad.md"
    _write_contract(
        contract,
        artifact_path="data/bad.csv",
        checksum="sha256:0000",
    )

    report = validate_sample_data.validate_contract(contract, repo_root=repo_root)

    assert not report.valid()
    assert "checksum mismatch" in report.artifacts[0].errors[0]


def test_validate_contract_without_front_matter_fails(tmp_path: Path) -> None:
    repo_root = tmp_path
    contract = repo_root / "docs" / "data" / "missing.md"
    contract.parent.mkdir(parents=True)
    contract.write_text("# Missing metadata\n", encoding="utf-8")

    report = validate_sample_data.validate_contract(contract, repo_root=repo_root)

    assert not report.valid()
    assert any("front matter" in error for error in report.errors)


def test_validate_contract_invalid_yaml_front_matter_reports_error(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    contract = repo_root / "docs" / "data" / "invalid.md"
    contract.parent.mkdir(parents=True)
    contract.write_text("---\nowner: [\n---\nbody\n", encoding="utf-8")

    report = validate_sample_data.validate_contract(contract, repo_root=repo_root)

    assert not report.valid()
    assert any("invalid YAML front matter" in error for error in report.errors)


def test_discover_contracts_skips_missing_directories(tmp_path: Path) -> None:
    repo_root = tmp_path
    contracts = validate_sample_data.discover_contracts(repo_root=repo_root)
    assert contracts == []
