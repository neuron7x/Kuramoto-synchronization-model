# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Architecture scanning utilities for GeoSync.

This module inspects the Python source tree and builds a dependency graph that
can be used to reason about architectural boundaries.  It intentionally keeps
the implementation self-contained and free of heavy third-party requirements
so that it can run inside CI or local developer environments without any
additional setup.

The scanner focuses on Python packages that live directly under the project
root (e.g. ``core`` or ``application``) and under ``src/``.  The resulting
``ArchitectureReport`` exposes helpers for computing strongly connected
components, orphan modules, and an aggregated summary that feeds both
documentation and automated health checks.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Set


@dataclass(frozen=True)
class ModuleInfo:
    """Represents a single Python module within the repository."""

    name: str
    path: Path
    internal_imports: Set[str] = field(default_factory=set)
    external_imports: Set[str] = field(default_factory=set)


@dataclass
class ArchitectureReport:
    """Holds the results of a repository scan."""

    modules: Mapping[str, ModuleInfo]
    dependencies: Mapping[str, Set[str]]
    reverse_dependencies: Mapping[str, Set[str]]
    cycles: List[List[str]]

    def orphan_modules(self) -> List[str]:
        """Modules that neither depend on nor are depended upon internally."""

        orphans: List[str] = []
        child_index = self._build_child_index()
        for name, module in self.modules.items():
            if self.dependencies.get(name) or self.reverse_dependencies.get(name):
                continue
            if module.internal_imports:
                # The module imports internal modules but nothing depends on it.
                # It is useful to surface these separately from true orphans.
                continue
            if child_index.get(name):
                # Package roots that merely re-export submodules should not be
                # treated as orphans.
                continue
            orphans.append(name)
        return sorted(orphans)

    def modules_without_dependents(self) -> List[str]:
        """Modules that are imported internally but not depended upon."""

        lonely: List[str] = []
        for name, module in self.modules.items():
            if module.internal_imports and not self.reverse_dependencies.get(name):
                lonely.append(name)
        return sorted(lonely)

    def _build_child_index(self) -> Mapping[str, Set[str]]:
        index: Dict[str, Set[str]] = defaultdict(set)
        for module in self.modules.keys():
            parts = module.split(".")
            for i in range(1, len(parts)):
                parent = ".".join(parts[:i])
                index[parent].add(module)
        return index

    def to_summary(self) -> str:
        """Render a human-readable summary of the scan."""

        lines = [
            "Architecture Scan Summary",
            "==========================",
            f"Total modules analyzed: {len(self.modules)}",
            f"Internal dependencies: {sum(len(v) for v in self.dependencies.values())}",
            f"Detected dependency cycles: {len(self.cycles)}",
        ]

        if self.cycles:
            lines.append("")
            lines.append("Cycles:")
            for idx, cycle in enumerate(self.cycles, start=1):
                lines.append(f"  {idx}. {' -> '.join(cycle)}")

        orphans = self.orphan_modules()
        if orphans:
            lines.append("")
            lines.append("Truly orphan modules (no internal edges):")
            for module in orphans:
                lines.append(f"  - {module}")

        lonely = self.modules_without_dependents()
        if lonely:
            lines.append("")
            lines.append("Modules without dependents:")
            for module in lonely:
                lines.append(f"  - {module}")

        return "\n".join(lines)


class ArchitectureScanner:
    """Scans the repository to build an ``ArchitectureReport``."""

    def __init__(self, root: Path, include: Sequence[Path] | None = None) -> None:
        self.root = root.resolve()
        if include is None:
            include = self._discover_default_includes()
        self.include = list(include)

    def _discover_default_includes(self) -> List[Path]:
        """Find Python package roots that should be analysed."""

        includes: List[Path] = []
        src_dir = self.root / "src"
        search_roots = [self.root]
        if src_dir.exists():
            search_roots.append(src_dir)

        for base in search_roots:
            for child in sorted(base.iterdir()):
                if not child.is_dir():
                    continue
                if child.name.startswith(".") or child.name == "__pycache__":
                    continue
                if base is self.root and child == src_dir:
                    continue
                if self._contains_python_package(child):
                    includes.append(child)

        return includes

    def _contains_python_package(self, directory: Path) -> bool:
        """Return True if the directory contains a Python package anywhere within."""

        stack: List[Path] = [directory]
        while stack:
            current = stack.pop()
            if (current / "__init__.py").exists():
                return True
            for child in current.iterdir():
                if not child.is_dir():
                    continue
                if child.name.startswith(".") or child.name == "__pycache__":
                    continue
                stack.append(child)
        return False

    def scan(self) -> ArchitectureReport:
        modules: Dict[str, ModuleInfo] = {}
        dependencies: Dict[str, Set[str]] = defaultdict(set)
        reverse_dependencies: Dict[str, Set[str]] = defaultdict(set)

        module_paths = {self._module_name(path): path for path in self._iter_python_files()}
        module_names = {name for name in module_paths.keys() if name}

        for name, path in module_paths.items():
            if not name:
                continue
            internal, external = self._collect_imports(name, path, module_names)
            modules[name] = ModuleInfo(
                name=name,
                path=path,
                internal_imports=internal,
                external_imports=external,
            )
            for dep in internal:
                dependencies[name].add(dep)
                reverse_dependencies[dep].add(name)

        cycles = self._detect_cycles(modules.keys(), dependencies)
        return ArchitectureReport(
            modules=modules,
            dependencies=dependencies,
            reverse_dependencies=reverse_dependencies,
            cycles=cycles,
        )

    def _iter_python_files(self) -> Iterable[Path]:
        seen: Set[Path] = set()
        for directory in self.include:
            if not directory.exists():
                continue
            for file_path in directory.rglob("*.py"):
                if "__pycache__" in file_path.parts:
                    continue
                if not file_path.exists():
                    continue
                normalized = file_path.resolve()
                if normalized in seen:
                    continue
                seen.add(normalized)
                yield normalized

    def _module_name(self, path: Path) -> str:
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            return ""

        parts = list(rel.with_suffix("").parts)
        if not parts:
            return ""
        if parts[0] == "src":
            parts = parts[1:]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _collect_imports(
        self, module_name: str, path: Path, known_modules: Set[str]
    ) -> tuple[Set[str], Set[str]]:
        internal: Set[str] = set()
        external: Set[str] = set()
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return internal, external

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return internal, external

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._classify_import(alias.name, internal, external, known_modules)
            elif isinstance(node, ast.ImportFrom):
                for target in self._resolve_from_import(module_name, node):
                    self._classify_import(target, internal, external, known_modules)

        return internal, external

    def _classify_import(
        self,
        target: str,
        internal: Set[str],
        external: Set[str],
        known_modules: Set[str],
    ) -> None:
        if not target:
            return
        canonical = self._resolve_internal_target(target, known_modules)
        if canonical:
            internal.add(canonical)
            return

        external.add(target.split(".")[0])

    def _resolve_internal_target(self, target: str, known_modules: Set[str]) -> str | None:
        if target in known_modules:
            return target

        # Imports that reference a package rather than a module should still be
        # treated as internal if we have any child modules.
        for module in known_modules:
            if module.startswith(target + "."):
                return target
        return None

    def _resolve_from_import(self, current_module: str, node: ast.ImportFrom) -> Set[str]:
        results: Set[str] = set()
        base_module = node.module or ""
        level = node.level or 0

        if level:
            current_parts = current_module.split(".")
            if level > len(current_parts):
                base_parts: List[str] = []
            else:
                base_parts = current_parts[: len(current_parts) - level]
            if base_module:
                base_parts.extend(base_module.split("."))
            base_module = ".".join(base_parts)

        if not node.names:
            if base_module:
                results.add(base_module)
            return results

        for alias in node.names:
            if alias.name == "*":
                if base_module:
                    results.add(base_module)
                continue
            if base_module:
                results.add(f"{base_module}.{alias.name}")
            else:
                results.add(alias.name)
        return results

    def _detect_cycles(
        self, modules: Iterable[str], dependencies: Mapping[str, Set[str]]
    ) -> List[List[str]]:
        cycles: List[List[str]] = []
        temp_mark: Set[str] = set()
        perm_mark: Set[str] = set()
        stack: List[str] = []

        def visit(node: str) -> None:
            if node in perm_mark:
                return
            if node in temp_mark:
                cycle_start_index = stack.index(node)
                cycles.append(stack[cycle_start_index:] + [node])
                return

            temp_mark.add(node)
            stack.append(node)
            for neighbor in dependencies.get(node, ()):
                visit(neighbor)
            temp_mark.remove(node)
            perm_mark.add(node)
            stack.pop()

        for module in modules:
            visit(module)
        return cycles


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze the GeoSync architecture")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print the textual summary to stdout",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    scanner = ArchitectureScanner(args.root)
    report = scanner.scan()
    if args.summary:
        print(report.to_summary())
    else:
        print(
            "Run with --summary to print a human-readable overview. "
            "The scanner is also designed to be imported for bespoke checks."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
