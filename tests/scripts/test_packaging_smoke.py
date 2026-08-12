# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Packaging smoke contract for repository script entrypoints.

The repository exposes console_scripts that target modules under ``scripts``.
This test keeps the build contract honest: the modules must be packaged by
setuptools and package directories used by entrypoints must carry
``__init__.py`` markers so clean wheel/editable installs do not depend on an
accidental repository-root ``PYTHONPATH``.
"""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"

# Modules migrated off repo-root ``sys.path`` hacks onto packaged imports
# (issue #945 ratchet drain). Each must import by its canonical dotted path —
# i.e. resolve as a packaged module, not via an accidental script-dir insert —
# and must carry no runtime path mutation in its source.
_MIGRATED_PACKAGED_MODULES: tuple[str, ...] = (
    "scripts.build_verification_report",
    "scripts.calibrate_controllers",
    "scripts.check_invariant_count_sync",
    "scripts.generate_openapi",
    "scripts.validate_dataset_schema",
    "scripts.validate_datasets",
    "scripts.validate_metrics",
    "tools.cns_program.build_release_manifest",
    "tools.cns_program.deploy_release_gate",
    "tools.cns_program.quality_gate",
    "tools.cns_program.regression_selftest",
    "tools.cns_program.verify_release_manifest",
    "tools.cns_program.verify_reports_contract",
    "tools.coverage.validate_coverage_targets",
    "tools.reset_wave_offline_benchmark",
)

_PATH_HACK_RE = re.compile(r"sys\.path\.(insert|append)\s*\(")


def _pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _entrypoint_module(target: str) -> str:
    module, _sep, _callable = target.partition(":")
    assert module, f"empty console-script module in {target!r}"
    return module


def test_scripts_console_entrypoints_are_packaged() -> None:
    payload = _pyproject()
    scripts = payload["project"]["scripts"]
    include = set(
        payload["tool"]["setuptools"]["packages"]["find"]["include"]
    )

    script_modules = {
        _entrypoint_module(target)
        for target in scripts.values()
        if _entrypoint_module(target).startswith("scripts.")
    }

    assert script_modules, "expected at least one scripts.* console-script target"
    assert {"scripts", "scripts.*"} <= include

    for module in sorted(script_modules):
        module_path = ROOT.joinpath(*module.split("."))
        assert (
            module_path.with_suffix(".py").exists() or (module_path / "__init__.py").exists()
        ), f"console-script module target is missing: {module}"

        package_parts = module.split(".")[:-1]
        for depth in range(1, len(package_parts) + 1):
            package_init = ROOT.joinpath(*package_parts[:depth], "__init__.py")
            assert package_init.exists(), f"missing package marker for {module}: {package_init}"


def test_migrated_modules_import_as_packaged() -> None:
    """Each migrated entrypoint resolves by its canonical dotted path.

    A successful ``import_module`` proves the module no longer relies on a
    self-inserted repo-root path to find its first-party dependencies.
    """
    for module in _MIGRATED_PACKAGED_MODULES:
        imported = importlib.import_module(module)
        assert imported.__name__ == module


def test_migrated_modules_carry_no_path_hack() -> None:
    """Migrated modules must not mutate ``sys.path`` at runtime."""
    for module in _MIGRATED_PACKAGED_MODULES:
        source = ROOT.joinpath(*module.split(".")).with_suffix(".py")
        assert source.exists(), f"migrated module source missing: {source}"
        text = source.read_text(encoding="utf-8")
        assert not _PATH_HACK_RE.search(text), (
            f"{module} still mutates sys.path; the #945 ratchet forbids re-adding it"
        )


def test_ci_entrypoints_are_explicitly_registered() -> None:
    payload = _pyproject()
    scripts = payload["project"]["scripts"]

    assert scripts["geosync-release-gate"] == "scripts.ci.release_gate:main"
    assert scripts["geosync-import-architecture"] == "scripts.ci.check_import_architecture:main"
    assert scripts["geosync-pai"] == "scripts.ci.compute_pai:main"
    assert scripts["geosync-scripts"] == "scripts.cli:main"
