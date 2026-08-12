# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Architecture auditing utilities for GeoSync.

This module provides tooling to inspect Python packages inside the
repository and build a representation of the current architecture. The
audit focuses on import relationships (module dependencies), data model
definitions, and several classes of conflicts that frequently appear in
large codebases (circular dependencies, divergent model definitions, and
missing modules referenced by imports).

The primary entry-point is :class:`ArchitectureAudit`, which can be used
programmatically or through the CLI interface implemented at the bottom
of the file.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

PYTHON_FILE_SUFFIXES: tuple[str, ...] = (".py", ".pyi")
STDLIB_MODULES: set[str] = set(getattr(sys, "stdlib_module_names", ()))


def _iter_python_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in PYTHON_FILE_SUFFIXES:
            yield path


def _module_name(root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(root)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py" or parts[-1] == "__init__.pyi":
        parts = parts[:-1]
    else:
        suffix_length = 3 if parts[-1].endswith(".py") else 4
        parts[-1] = parts[-1][:-suffix_length]
    prefix: list[str] = []
    if (root / "__init__.py").exists() or (root / "__init__.pyi").exists():
        prefix.append(root.name)
    full_parts = [*prefix, *parts]
    return ".".join(part for part in full_parts if part)


def _extract_imports(tree: ast.AST, module_name: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base_module = node.module or ""
            current_parts = module_name.split(".") if module_name else []
            if node.level:
                prefix = current_parts[: -node.level] if node.level <= len(current_parts) else []
            else:
                prefix = []
            base_parts = base_module.split(".") if base_module else []
            resolved_base_parts = [*prefix, *base_parts]
            resolved_base = ".".join(part for part in resolved_base_parts if part)

            if node.module:
                if resolved_base:
                    imports.add(resolved_base)

                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if resolved_base:
                        imports.add(f"{resolved_base}.{alias.name}")
                    else:
                        imports.add(alias.name)
            else:
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if resolved_base:
                        imports.add(f"{resolved_base}.{alias.name}")
                    else:
                        imports.add(alias.name)
    return imports


def _extract_dataclasses(tree: ast.AST) -> dict[str, set[str]]:
    dataclasses: dict[str, set[str]] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.ClassDef):
            decorators = {getattr(dec, "id", None) for dec in node.decorator_list}
            if "dataclass" in decorators:
                fields: set[str] = set()
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        fields.add(stmt.target.id)
                dataclasses[node.name] = fields
    return dataclasses


def _extract_typeddicts(tree: ast.AST) -> dict[str, set[str]]:
    definitions: dict[str, set[str]] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.ClassDef):
            base_names = {
                getattr(base, "id", None) for base in node.bases if isinstance(base, ast.Name)
            }
            if "TypedDict" in base_names:
                keys: set[str] = set()
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        keys.add(stmt.target.id)
                definitions[node.name] = keys
    return definitions


@dataclass(slots=True)
class ModuleInfo:
    name: str
    path: Path
    imports: set[str] = field(default_factory=set)
    dataclasses: dict[str, set[str]] = field(default_factory=dict)
    typeddicts: dict[str, set[str]] = field(default_factory=dict)


@dataclass(slots=True)
class Conflict:
    type: str
    identifier: str
    locations: list[str]
    details: str


@dataclass(slots=True)
class ArchitectureReport:
    modules: dict[str, ModuleInfo]
    cycles: list[list[str]]
    conflicts: list[Conflict]
    dangling_dependencies: dict[str, set[str]]

    def to_dict(self) -> dict[str, object]:
        return {
            "modules": {
                name: {
                    "path": str(info.path),
                    "imports": sorted(info.imports),
                    "dataclasses": {k: sorted(v) for k, v in info.dataclasses.items()},
                    "typeddicts": {k: sorted(v) for k, v in info.typeddicts.items()},
                }
                for name, info in sorted(self.modules.items())
            },
            "cycles": self.cycles,
            "conflicts": [
                {
                    "type": conf.type,
                    "identifier": conf.identifier,
                    "locations": conf.locations,
                    "details": conf.details,
                }
                for conf in self.conflicts
            ],
            "dangling_dependencies": {
                module: sorted(deps) for module, deps in self.dangling_dependencies.items()
            },
        }


class ArchitectureAudit:
    def __init__(self, roots: Sequence[Path] | None = None) -> None:
        if roots is None:
            roots = (
                Path("src"),
                Path("application"),
                Path("core"),
                Path("domain"),
                Path("execution"),
                Path("strategies"),
            )
        self.roots = [Path(root) for root in roots if Path(root).exists()]

    def analyze(self) -> ArchitectureReport:
        modules: dict[str, ModuleInfo] = {}
        for root in self.roots:
            for file_path in _iter_python_files(root):
                try:
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                try:
                    tree = ast.parse(content)
                except SyntaxError:
                    continue
                module_name = _module_name(root, file_path)
                module_info = ModuleInfo(
                    name=module_name,
                    path=file_path,
                    imports=_extract_imports(tree, module_name),
                    dataclasses=_extract_dataclasses(tree),
                    typeddicts=_extract_typeddicts(tree),
                )
                modules[module_name] = module_info

        cycles = self._detect_cycles(modules)
        conflicts = self._detect_conflicts(modules)
        dangling = self._detect_dangling_dependencies(modules)
        return ArchitectureReport(
            modules=modules,
            cycles=cycles,
            conflicts=conflicts,
            dangling_dependencies=dangling,
        )

    @staticmethod
    def _detect_cycles(modules: dict[str, ModuleInfo]) -> list[list[str]]:
        adjacency = {name: info.imports for name, info in modules.items()}
        visited: set[str] = set()
        stack: set[str] = set()
        path: list[str] = []
        cycles: list[list[str]] = []

        def dfs(node: str) -> None:
            visited.add(node)
            stack.add(node)
            path.append(node)
            for neighbor in adjacency.get(node, set()):
                if neighbor not in modules:
                    continue
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in stack:
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:].copy())
            path.pop()
            stack.remove(node)

        for module_name in modules:
            if module_name not in visited:
                dfs(module_name)
        return cycles

    @staticmethod
    def _detect_conflicts(modules: dict[str, ModuleInfo]) -> list[Conflict]:
        conflicts: list[Conflict] = []

        def process(
            definitions: dict[str, list[tuple[str, set[str]]]],
            *,
            conflict_type: str,
            entity_label: str,
        ) -> None:
            for name, entries in definitions.items():
                signature_sets = {frozenset(fields) for _, fields in entries}
                if len(signature_sets) > 1:
                    locations = [module for module, _ in entries]
                    conflicts.append(
                        Conflict(
                            type=conflict_type,
                            identifier=name,
                            locations=locations,
                            details=f"Conflicting {entity_label} definitions detected",
                        )
                    )

        dataclass_defs: dict[str, list[tuple[str, set[str]]]] = {}
        typeddict_defs: dict[str, list[tuple[str, set[str]]]] = {}
        for module_name, info in modules.items():
            for cls_name, fields in info.dataclasses.items():
                dataclass_defs.setdefault(cls_name, []).append((module_name, fields))
            for td_name, keys in info.typeddicts.items():
                typeddict_defs.setdefault(td_name, []).append((module_name, keys))

        process(dataclass_defs, conflict_type="dataclass", entity_label="dataclass")
        process(typeddict_defs, conflict_type="typeddict", entity_label="TypedDict")
        return conflicts

    @staticmethod
    def _detect_dangling_dependencies(
        modules: dict[str, ModuleInfo],
    ) -> dict[str, set[str]]:
        module_names = set(modules)
        dangling: dict[str, set[str]] = {}
        for name, info in modules.items():
            missing: set[str] = set()
            for dep in info.imports:
                top_level = dep.split(".")[0]
                if dep in module_names:
                    continue
                if top_level in STDLIB_MODULES:
                    continue
                missing.add(dep)
            if missing:
                dangling[name] = missing
        return dangling


def run_audit(paths: Iterable[str]) -> ArchitectureReport:
    resolved_paths = [Path(path) for path in paths]
    auditor = ArchitectureAudit(resolved_paths)
    return auditor.analyze()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GeoSync architecture audit")
    parser.add_argument(
        "paths",
        nargs="*",
        default=None,
        help="Optional list of root directories to inspect (defaults to key project packages)",
    )
    parser.add_argument("--output", "-o", type=Path, help="Write JSON report to the specified file")
    args = parser.parse_args(argv)

    report = run_audit(args.paths) if args.paths else ArchitectureAudit().analyze()
    output_data = json.dumps(report.to_dict(), indent=2)

    if args.output:
        args.output.write_text(output_data, encoding="utf-8")
    else:
        print(output_data)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
