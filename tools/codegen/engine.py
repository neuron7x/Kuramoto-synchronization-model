from __future__ import annotations

"""Deterministic code generation engine."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import CodegenConfig, TaskConfig
from .generators.base import GenerationRequest
from .registry import generator_registry
from .runtime.fingerprint import stable_hash
from .runtime.publisher import Artifact, ArtifactPublisher
from .runtime.smoke import SmokeTestResult, build_smoke_test
from .runtime.versioning import VersionManager


@dataclass(slots=True)
class GenerationSummary:
    task_name: str
    output_path: Path
    updated: bool
    diagnostics: dict[str, str]
    smoke: list[SmokeTestResult]


class CodegenEngine:
    def __init__(self, config: CodegenConfig) -> None:
        self.config = config
        self.version_manager = VersionManager(config.runtime.version_file)
        self.cache_dir = config.runtime.cache_dir
        self.artifacts_dir = config.runtime.artifacts_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def run(self, *, tasks: Iterable[str] | None = None, check: bool = False) -> list[GenerationSummary]:
        selected = set(tasks) if tasks else None
        summaries: list[GenerationSummary] = []
        for task in sorted(self.config.tasks, key=lambda t: t.name):
            if selected and task.name not in selected:
                continue
            summary = self._run_task(task, check=check)
            summaries.append(summary)
        return summaries

    def _run_task(self, task: TaskConfig, *, check: bool) -> GenerationSummary:
        generator = generator_registry.create(task.generator)
        sources = self._load_sources(task)
        template = task.template
        request = GenerationRequest(
            name=task.name,
            sources=sources,
            template=template,
            output_path=task.output,
            metadata=task.metadata,
            project_root=Path(task.metadata.get("project_root")),
        )
        fingerprint = self._compute_fingerprint(task, sources)
        cache_file = self.cache_dir / f"{task.name}.sha256"
        previous_fingerprint = cache_file.read_text(encoding="utf-8") if cache_file.exists() else None
        output_path = task.output
        existing_content = output_path.read_text(encoding="utf-8") if output_path.exists() else None
        result = generator.generate(request)
        updated = existing_content != result.content
        if check and updated:
            self._write_diff(task, existing_content or "", result.content)
            raise RuntimeError(f"Task '{task.name}' produced changes during --check mode")
        if task.update_mode != "manual" and (updated or task.update_mode == "always"):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result.content, encoding="utf-8")
            cache_file.write_text(fingerprint, encoding="utf-8")
        elif previous_fingerprint != fingerprint:
            cache_file.write_text(fingerprint, encoding="utf-8")
        smoke_results = self._run_smoke_tests(task, output_path)
        if task.publish_artifact:
            self._publish(task, output_path)
        diagnostics = {
            "fingerprint": fingerprint,
            "previous_fingerprint": previous_fingerprint or "",
        }
        return GenerationSummary(task.name, output_path, updated, diagnostics, smoke_results)

    def _load_sources(self, task: TaskConfig) -> dict[str, dict]:
        import json
        import yaml

        payloads: dict[str, dict] = {}
        for source in sorted(task.sources):
            content = source.read_text(encoding="utf-8")
            if source.suffix in {".yaml", ".yml"}:
                data = yaml.safe_load(content) or {}
            else:
                data = json.loads(content)
            payloads[source.name] = data
        return payloads

    def _compute_fingerprint(self, task: TaskConfig, sources: dict[str, dict]) -> str:
        parts: list[str] = [task.name, task.generator]
        for name in sorted(sources):
            parts.append(name)
            parts.append(str(sources[name]))
        if task.template:
            parts.append(task.template.read_text(encoding="utf-8"))
        parts.append(str(sorted(task.metadata.items())))
        return stable_hash(parts)

    def _run_smoke_tests(self, task: TaskConfig, artifact_path: Path) -> list[SmokeTestResult]:
        results: list[SmokeTestResult] = []
        for config in task.smoke_tests:
            smoke = build_smoke_test(config, artifact_path, artifact_path.parent)
            results.append(smoke.run())
        return results

    def _publish(self, task: TaskConfig, artifact_path: Path) -> None:
        publisher = ArtifactPublisher(self.artifacts_dir, self.version_manager.resolve())
        publisher.publish(task.name, [Artifact(task.name, artifact_path)])

    def _write_diff(self, task: TaskConfig, old: str, new: str) -> None:
        if not task.diff_strict:
            return
        from difflib import unified_diff

        diff_lines = unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"{task.name}:before",
            tofile=f"{task.name}:after",
        )
        diff_path = self.cache_dir / f"{task.name}.diff"
        diff_path.write_text("".join(diff_lines), encoding="utf-8")
