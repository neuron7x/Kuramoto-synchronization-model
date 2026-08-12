# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""High-level orchestration for API governance workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ApiRegistry
from .generator import ApiArtifactGenerator, GeneratedArtifacts
from .validation import ApiValidationReport, validate_registry


@dataclass(slots=True)
class GovernanceOutcome:
    """Result of executing a governance run."""

    report: ApiValidationReport
    artifacts: GeneratedArtifacts | None


class ApiGovernanceRunner:
    """Coordinate validation and artifact generation for the API registry."""

    def __init__(self, registry: ApiRegistry, *, repo_root: Path) -> None:
        self._registry = registry
        self._repo_root = repo_root

    def validate(self) -> ApiValidationReport:
        """Run validation checks against the loaded registry."""

        return validate_registry(self._registry)

    def generate_artifacts(
        self,
        *,
        clients_dir: Path,
        docs_dir: Path,
        examples_dir: Path,
        visualization_path: Path | None = None,
    ) -> GeneratedArtifacts:
        """Materialise code and documentation artifacts."""

        generator = ApiArtifactGenerator(self._registry, repo_root=self._repo_root)
        return generator.generate(
            clients_dir=clients_dir,
            docs_dir=docs_dir,
            examples_dir=examples_dir,
            visualization_path=visualization_path,
        )

    def orchestrate(
        self,
        *,
        clients_dir: Path,
        docs_dir: Path,
        examples_dir: Path,
        visualization_path: Path | None = None,
        fail_on_warnings: bool = False,
    ) -> GovernanceOutcome:
        """Validate the registry and optionally generate artifacts."""

        report = self.validate()
        if report.errors:
            report.raise_for_errors()
        if fail_on_warnings and report.warnings:
            warnings = "\n - ".join(report.warnings)
            raise ValueError(f"Validation warnings treated as errors:\n - {warnings}")
        artifacts = self.generate_artifacts(
            clients_dir=clients_dir,
            docs_dir=docs_dir,
            examples_dir=examples_dir,
            visualization_path=visualization_path,
        )
        return GovernanceOutcome(report=report, artifacts=artifacts)
