from __future__ import annotations

"""Smoke test execution primitives."""

import importlib
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import SmokeTestConfig


@dataclass(slots=True)
class SmokeTestResult:
    name: str
    success: bool
    details: str | None = None


class SmokeTest(Protocol):
    def run(self) -> SmokeTestResult: ...


class ContainsStringTest:
    def __init__(self, config: SmokeTestConfig, artifact_path: Path) -> None:
        self.config = config
        self.artifact_path = artifact_path

    def run(self) -> SmokeTestResult:
        needle = self.config.options.get("needle")
        if not needle:
            return SmokeTestResult(self.config.name, False, "Missing 'needle' option")
        content = self.artifact_path.read_text(encoding="utf-8")
        success = needle in content
        return SmokeTestResult(
            self.config.name,
            success,
            None if success else f"Expected substring '{needle}' not found in {self.artifact_path}",
        )


class ImportModuleTest:
    def __init__(self, config: SmokeTestConfig) -> None:
        self.config = config

    def run(self) -> SmokeTestResult:
        module_name = self.config.options.get("module")
        if not module_name:
            return SmokeTestResult(self.config.name, False, "Missing 'module' option")
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - defensive logging
            return SmokeTestResult(self.config.name, False, f"Import failed: {exc}")
        return SmokeTestResult(self.config.name, True)


class ExecuteScriptTest:
    def __init__(self, config: SmokeTestConfig, working_dir: Path) -> None:
        self.config = config
        self.working_dir = working_dir

    def run(self) -> SmokeTestResult:
        script = self.config.options.get("path")
        if not script:
            return SmokeTestResult(self.config.name, False, "Missing 'path' option")
        script_path = (self.working_dir / script).resolve()
        try:
            runpy.run_path(str(script_path))
        except Exception as exc:  # pragma: no cover - defensive logging
            return SmokeTestResult(self.config.name, False, f"Execution failed: {exc}")
        return SmokeTestResult(self.config.name, True)


def build_smoke_test(
    config: SmokeTestConfig, artifact_path: Path, working_dir: Path
) -> SmokeTest:
    if config.type == "contains":
        return ContainsStringTest(config, artifact_path)
    if config.type == "import":
        return ImportModuleTest(config)
    if config.type == "exec":
        return ExecuteScriptTest(config, working_dir)
    raise ValueError(f"Unknown smoke test type: {config.type}")
