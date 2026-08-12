#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate examples manifest coverage and pinned dependencies."""

from __future__ import annotations

from pathlib import Path

import yaml


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = repo_root / "docs" / "examples" / "examples_manifest.yaml"
    examples_dir = repo_root / "examples"
    requirements_lock = repo_root / "requirements.lock"

    if not manifest_path.exists():
        print(f"Manifest missing: {manifest_path}")
        return 1

    manifest = yaml.safe_load(manifest_path.read_text())
    if not isinstance(manifest, dict) or "examples" not in manifest:
        print("Manifest must be a mapping with an 'examples' key")
        return 1

    example_entries = manifest["examples"]
    if not isinstance(example_entries, list):
        print("Manifest 'examples' must be a list")
        return 1

    manifest_paths: set[str] = set()
    for entry in example_entries:
        if not isinstance(entry, dict) or "path" not in entry:
            print(f"Invalid manifest entry: {entry}")
            return 1
        manifest_paths.add(entry["path"])

        if "seed" not in entry:
            print(f"Missing seed for {entry['path']}")
            return 1
        if "dependencies" not in entry:
            print(f"Missing dependencies for {entry['path']}")
            return 1

    actual_paths = {
        str(path.relative_to(repo_root))
        for path in examples_dir.glob("*.py")
        if path.name != "__init__.py"
    }

    missing = actual_paths - manifest_paths
    extra = manifest_paths - actual_paths

    if missing:
        print("Missing examples in manifest:")
        for path in sorted(missing):
            print(f"  - {path}")

    if extra:
        print("Manifest references missing example files:")
        for path in sorted(extra):
            print(f"  - {path}")

    if missing or extra:
        return 1

    if not requirements_lock.exists():
        print("requirements.lock not found; cannot validate pinned dependencies")
        return 1

    lock_text = requirements_lock.read_text()
    dependency_errors = []
    for entry in example_entries:
        dependencies = entry.get("dependencies", [])
        if not dependencies:
            continue
        if not isinstance(dependencies, list):
            dependency_errors.append(f"Dependencies must be a list for {entry['path']}")
            continue
        for dep in dependencies:
            if dep not in lock_text:
                dependency_errors.append(
                    f"Dependency '{dep}' for {entry['path']} not found in requirements.lock"
                )

    if dependency_errors:
        print("Dependency validation errors:")
        for error in dependency_errors:
            print(f"  - {error}")
        return 1

    print("Examples manifest validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
