# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate dataset provenance metadata sidecars.

The validator enforces:
* Every CSV under ``data/`` has a ``.meta.json`` sidecar
* Sidecars contain the required provenance fields
* Contracted datasets match their registered schema_version and dataset_id
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Iterable, List

os.environ.setdefault("GEOSYNC_LIGHT_DATA_IMPORT", "1")

# Packaged import (``scripts.validate_datasets``): core.data resolves from the
# installed wheel, not an accidental repo-root sys.path insert (#945). The
# os.environ side effect above is an E402-exempt pre-import hook (ruff).
from core.data.dataset_contracts import DatasetContract, iter_contracts
from core.data.fingerprint import (
    compute_dataset_fingerprint,
    write_fingerprint_artifact,
)

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FIELDS = {
    "dataset_id",
    "origin",
    "description",
    "creation_method",
    "temporal_coverage",
    "schema_version",
    "intended_use",
    "forbidden_use",
}


def _load_metadata(path: Path) -> tuple[dict, list[str]]:
    errors: list[str] = []
    if not path.exists():
        return {}, [f"Missing metadata file: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"Invalid JSON in {path}: {exc}"]
    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        errors.append(f"{path} missing fields: {missing}")
    for field in REQUIRED_FIELDS:
        if field in data and (data[field] is None or str(data[field]).strip() == ""):
            errors.append(f"{path} has empty field: {field}")
    return data, errors


def _validate_contract_metadata(contract: DatasetContract) -> list[str]:
    metadata, errors = _load_metadata(contract.meta_path)
    if errors:
        return errors

    if metadata.get("dataset_id") != contract.dataset_id:
        errors.append(
            f"{contract.meta_path} dataset_id mismatch "
            f"(expected {contract.dataset_id}, found {metadata.get('dataset_id')})"
        )
    if metadata.get("schema_version") != contract.schema_version:
        errors.append(
            f"{contract.meta_path} schema_version mismatch "
            f"(expected {contract.schema_version}, found {metadata.get('schema_version')})"
        )
    if metadata.get("origin") != contract.origin:
        errors.append(
            f"{contract.meta_path} origin mismatch "
            f"(expected {contract.origin}, found {metadata.get('origin')})"
        )
    if metadata.get("intended_use") != contract.intended_use:
        errors.append(
            f"{contract.meta_path} intended_use mismatch "
            f"(expected {contract.intended_use}, found {metadata.get('intended_use')})"
        )
    return errors


def _git_ignored(paths: list[Path]) -> set[Path]:
    """Return the subset of *paths* that ``git`` reports as ignored.

    The validator scans ``data/`` for orphan CSVs, but local research
    artefacts (e.g. multi-megabyte Dukascopy snapshots) are routinely
    placed there and listed in ``.gitignore``. Those files must not
    raise a metadata-sidecar violation; they are not part of the
    delivered dataset surface.
    """

    if not paths:
        return set()
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--stdin", "-z"],
            input="\0".join(str(p) for p in paths),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, FileNotFoundError):
        return set()
    if result.returncode not in {0, 1}:
        # 0 = at least one ignored, 1 = none ignored, others = real failure.
        return set()
    ignored: set[Path] = set()
    for raw in result.stdout.split("\0"):
        token = raw.strip()
        if token:
            ignored.add(Path(token).resolve())
    return ignored


def _discover_csvs(base: Path) -> Iterable[Path]:
    candidates = list(base.rglob("*.csv"))
    ignored = _git_ignored(candidates)
    return [p for p in candidates if p.resolve() not in ignored]


def validate_all() -> list[str]:
    """Return a list of validation errors."""

    errors: List[str] = []
    seen_ids: set[str] = set()
    registered_paths = {contract.path.resolve() for contract in iter_contracts()}

    for contract in iter_contracts():
        if contract.dataset_id in seen_ids:
            errors.append(f"Duplicate dataset_id in registry: {contract.dataset_id}")
        seen_ids.add(contract.dataset_id)
        errors.extend(_validate_contract_metadata(contract))

    for csv_path in _discover_csvs(ROOT / "data"):
        if csv_path.resolve() not in registered_paths:
            meta_path = csv_path.with_suffix(csv_path.suffix + ".meta.json")
            if not meta_path.exists():
                errors.append(f"Unregistered dataset without metadata: {csv_path}")

    return errors


def write_all_fingerprints(output_dir: Path) -> list[Path]:
    """Write fingerprint artifacts for all registered datasets."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for contract in iter_contracts():
        fingerprint = compute_dataset_fingerprint(contract)
        paths.append(write_fingerprint_artifact(fingerprint, output_dir=output_dir))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate dataset metadata sidecars.")
    parser.add_argument(
        "--write-fingerprints",
        type=Path,
        help="Optional directory to write dataset fingerprint artifacts after validation",
    )
    args = parser.parse_args(argv)
    errors = validate_all()
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 1
    print("All dataset metadata sidecars are present and valid.")
    if args.write_fingerprints:
        written = write_all_fingerprints(args.write_fingerprints)
        print(f"Fingerprint artifacts written: {', '.join(str(p) for p in written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
