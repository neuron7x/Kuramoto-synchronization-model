"""Comprehensive code-style enforcement pipeline for TradePulse."""

from __future__ import annotations

# SPDX-License-Identifier: MIT

import ast
import os
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, Sequence

from scripts.commands.base import CommandError, ensure_tools_exist, register, run_subprocess

LOGGER = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]

PYTHON_SUFFIXES = {".py", ".pyi", ".pyw"}
TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".pyw",
    ".pyx",
    ".pxd",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".toml",
    ".cfg",
    ".ini",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".rst",
    ".txt",
    ".sh",
    ".ps1",
    ".cjs",
    ".mjs",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".scss",
}
TEXT_FILE_NAMES = {".env", ".pre-commit-config.yaml", "Dockerfile", "Makefile", "README", "LICENSE"}
IGNORED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".nox",
    ".tox",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    "target",
    "venv",
    ".venv",
    "env",
    "site-packages",
}
SPDX_HEADER = "# SPDX-License-Identifier: MIT"
REV_LINE_PATTERN = re.compile(r"^\s*rev:\s*(?P<rev>['\"]?)(?P<value>[^'\"#]+)\1\s*(?:#.*)?$")
DISALLOWED_REVS = {"master", "main", "head", "latest", "stable"}


@dataclass
class StyleIssue:
    """Container describing a policy violation."""

    category: str
    path: Path | None
    detail: str

    def __str__(self) -> str:  # pragma: no cover - debug aid
        location = f"{self.path}: " if self.path else ""
        return f"{location}{self.category} – {self.detail}"


@dataclass
class StyleContext:
    """Shared execution state for the style pipeline."""

    check_only: bool
    issues: list[StyleIssue] = field(default_factory=list)

    def add_issue(self, category: str, detail: str, path: Path | None = None) -> None:
        self.issues.append(StyleIssue(category=category, detail=detail, path=path))

    def has_issues(self) -> bool:
        return bool(self.issues)


@dataclass
class StyleTask:
    """Declarative description of an individual pipeline step."""

    name: str
    action: Callable[[StyleContext], None]
    required_tools: Sequence[str] = ()

    def run(self, context: StyleContext) -> None:
        LOGGER.debug("Starting style task '%s'", self.name)
        try:
            if self.required_tools:
                ensure_tools_exist(self.required_tools)
        except CommandError as exc:
            LOGGER.error("Skipping task '%s': %s", self.name, exc)
            context.add_issue(self.name, f"Missing required tooling: {exc}")
            return

        try:
            self.action(context)
        except CommandError as exc:
            LOGGER.error("Task '%s' failed: %s", self.name, exc)
            context.add_issue(self.name, str(exc))
        else:
            LOGGER.debug("Completed style task '%s'", self.name)


def _iter_repository_files(paths: Sequence[Path]) -> Iterator[Path]:
    for base in paths:
        if not base.exists():
            LOGGER.debug("Skipping missing path %s", base)
            continue
        if base.is_file():
            yield base
            continue
        for candidate in base.rglob("*"):
            if not candidate.is_file():
                continue
            if any(part in IGNORED_DIR_NAMES for part in candidate.parts):
                continue
            yield candidate


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    return path.name in TEXT_FILE_NAMES


def _normalize_text_files(context: StyleContext, files: Iterable[Path]) -> None:
    for path in files:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            context.add_issue("Encoding", f"Unable to read file ({exc})", path)
            continue

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            context.add_issue("Encoding", f"Non-UTF-8 content detected ({exc})", path)
            continue

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.endswith("\n") and normalized:
            normalized = f"{normalized}\n"
        if normalized == text:
            continue
        if context.check_only:
            context.add_issue("Normalization", "Non-normalized line endings detected", path)
            continue
        try:
            path.write_text(normalized, encoding="utf-8", newline="\n")
        except OSError as exc:  # pragma: no cover - filesystem errors are environment specific
            context.add_issue("Normalization", f"Unable to write normalized content ({exc})", path)


def _run_python_formatters(context: StyleContext, targets: Sequence[str]) -> None:
    if not targets:
        LOGGER.info("No Python targets discovered; skipping formatters.")
        return

    black_cmd = ["black", "--config", "pyproject.toml", *targets]
    if context.check_only:
        black_cmd.insert(1, "--check")
        black_cmd.insert(2, "--diff")
    run_subprocess(black_cmd)

    isort_cmd = ["isort", "--settings-path", "pyproject.toml", *targets]
    if context.check_only:
        isort_cmd.insert(1, "--check-only")
        isort_cmd.insert(2, "--diff")
    run_subprocess(isort_cmd)


def _run_python_linters(context: StyleContext, targets: Sequence[str]) -> None:
    if not targets:
        return

    ruff_cmd = ["ruff", "check", "--config", "pyproject.toml", *targets]
    if not context.check_only:
        ruff_cmd.append("--fix")
    run_subprocess(ruff_cmd)

    mypy_cmd = ["mypy", "--config-file", "pyproject.toml", *targets]
    run_subprocess(mypy_cmd)


def _ensure_pre_commit(context: StyleContext) -> None:
    if os.getenv("PRE_COMMIT"):
        LOGGER.debug(
            "Detected PRE_COMMIT environment variable; skipping nested pre-commit invocation."
        )
        return

    config = REPO_ROOT / ".pre-commit-config.yaml"
    if not config.exists():
        context.add_issue("pre-commit", "Missing .pre-commit-config.yaml")
        return

    run_subprocess(["pre-commit", "install", "--install-hooks"])
    command = ["pre-commit", "run", "--all-files", "--show-diff-on-failure"]
    run_subprocess(command)


def _ensure_license_headers(context: StyleContext, python_files: Iterable[Path]) -> None:
    for path in python_files:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            context.add_issue("License", f"Unable to read file ({exc})", path)
            continue

        if SPDX_HEADER in source.splitlines()[:5]:
            continue

        insertion_index = 0
        shebang = source.startswith("#!")
        if shebang:
            insertion_index = 1

        try:
            module = ast.parse(source)
        except SyntaxError as exc:
            context.add_issue("License", f"Unable to parse module ({exc})", path)
            continue

        if module.body and isinstance(module.body[0], ast.Expr) and isinstance(
            getattr(module.body[0], "value", None), ast.Constant
        ) and isinstance(module.body[0].value.value, str):
            docstring_end = module.body[0].end_lineno or 0
            insertion_index = max(insertion_index, docstring_end)

        lines = source.splitlines()
        if any(SPDX_HEADER in line for line in lines[: insertion_index + 3]):
            continue

        if context.check_only:
            context.add_issue("License", "Missing SPDX license header", path)
            continue

        lines.insert(insertion_index, SPDX_HEADER)
        updated = "\n".join(lines)
        if not updated.endswith("\n"):
            updated += "\n"
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError as exc:  # pragma: no cover - environment dependent
            context.add_issue("License", f"Unable to update license header ({exc})", path)


def _resolve_module_name(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT)
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _build_import_graph(python_files: Iterable[Path]) -> tuple[Mapping[str, Path], Mapping[str, set[str]]]:
    modules: dict[str, Path] = {}
    graph: dict[str, set[str]] = {}
    for path in python_files:
        try:
            module_name = _resolve_module_name(path)
        except ValueError:
            LOGGER.debug("Skipping file outside repository root: %s", path)
            continue
        modules[module_name] = path

    for module_name, path in modules.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError) as exc:
            LOGGER.debug("Skipping module %s due to parse error: %s", module_name, exc)
            continue

        dependencies: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = _match_known_module(alias.name, modules)
                    if resolved and resolved != module_name:
                        dependencies.add(resolved)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                resolved = _resolve_relative_import(module_name, node.level, base)
                if resolved is not None:
                    target = _match_known_module(resolved, modules)
                    if target and target != module_name:
                        dependencies.add(target)
        graph[module_name] = dependencies

    return modules, graph


def _match_known_module(import_path: str, modules: Mapping[str, Path]) -> str | None:
    candidate = import_path
    while candidate:
        if candidate in modules:
            return candidate
        if "." not in candidate:
            break
        candidate = candidate.rsplit(".", 1)[0]
    return None


def _resolve_relative_import(module_name: str, level: int, base: str) -> str | None:
    if level == 0:
        return base
    parent_parts = module_name.split(".")
    if len(parent_parts) < level:
        return base if base else None
    resolved_parts = parent_parts[:-level]
    if base:
        resolved_parts.extend(base.split("."))
    return ".".join(resolved_parts) if resolved_parts else base or None


def _find_cycles(graph: Mapping[str, set[str]]) -> list[list[str]]:
    visited: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        stack.append(node)
        on_stack.add(node)
        for neighbor in graph.get(node, ()):  # pragma: no branch - loop is core logic
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in on_stack:
                cycle = stack[stack.index(neighbor) :].copy()
                if cycle and cycle not in cycles:
                    cycles.append(cycle)
        stack.pop()
        on_stack.remove(node)

    for module in graph:
        if module not in visited:
            dfs(module)

    return cycles


def _check_for_import_cycles(context: StyleContext, python_files: Iterable[Path]) -> None:
    modules, graph = _build_import_graph(python_files)
    if not modules:
        return
    cycles = _find_cycles(graph)
    for cycle in cycles:
        human_cycle = " -> ".join(cycle + [cycle[0]])
        context.add_issue("Imports", f"Cyclic dependency detected: {human_cycle}")


def _validate_pre_commit_versions(context: StyleContext) -> None:
    config = REPO_ROOT / ".pre-commit-config.yaml"
    if not config.exists():
        context.add_issue("pre-commit", "Missing .pre-commit-config.yaml")
        return

    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        context.add_issue("pre-commit", f"Unable to read configuration ({exc})")
        return

    for number, line in enumerate(lines, start=1):
        match = REV_LINE_PATTERN.search(line)
        if not match:
            continue
        value = match.group("value").strip().lower()
        if value in DISALLOWED_REVS or value in {"", "none"}:
            context.add_issue(
                "pre-commit",
                f"Unpinned revision '{value}' detected on line {number}",
                config,
            )


def _execute_pipeline(tasks: Sequence[StyleTask], context: StyleContext) -> None:
    for task in tasks:
        task.run(context)

    if context.has_issues():
        summary = "\n".join(str(issue) for issue in context.issues)
        raise CommandError(f"Style enforcement detected issues:\n{summary}")


def build_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "style",
        help="Auto-format source files and enforce repository style rules.",
    )
    parser.set_defaults(command="style", handler=handle)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[],
        help="Optional subset of paths to process. Defaults to the entire repository.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run in verification mode without modifying files.",
    )
    parser.add_argument(
        "--skip-pre-commit",
        action="store_true",
        help="Skip pre-commit installation and hook execution.",
    )
    parser.add_argument(
        "--skip-license",
        action="store_true",
        help="Skip SPDX license header enforcement.",
    )
    parser.add_argument(
        "--skip-cycle-check",
        action="store_true",
        help="Skip cyclic import dependency detection.",
    )


@register("style")
def handle(args) -> int:
    paths = args.paths or [REPO_ROOT]
    context = StyleContext(check_only=bool(args.check))

    all_files = list(_iter_repository_files(paths))
    python_files = [path for path in all_files if path.suffix.lower() in PYTHON_SUFFIXES]
    python_targets = [str(path) for path in python_files]
    text_files = [path for path in all_files if _is_text_file(path)]

    tasks: list[StyleTask] = [
        StyleTask(
            "Text normalization",
            lambda ctx: _normalize_text_files(ctx, text_files),
        ),
        StyleTask(
            "Python formatters",
            lambda ctx: _run_python_formatters(ctx, python_targets),
            required_tools=("black", "isort"),
        ),
        StyleTask(
            "Python linters",
            lambda ctx: _run_python_linters(ctx, python_targets),
            required_tools=("ruff", "mypy"),
        ),
        StyleTask(
            "Tool version pinning",
            _validate_pre_commit_versions,
        ),
    ]

    if not args.skip_license:
        tasks.append(
            StyleTask(
                "License headers",
                lambda ctx: _ensure_license_headers(ctx, python_files),
            )
        )

    if not args.skip_cycle_check:
        tasks.append(
            StyleTask(
                "Import cycles",
                lambda ctx: _check_for_import_cycles(ctx, python_files),
            )
        )

    if not args.skip_pre_commit:
        tasks.append(
            StyleTask(
                "pre-commit",
                _ensure_pre_commit,
                required_tools=("pre-commit",),
            )
        )

    _execute_pipeline(tasks, context)
    LOGGER.info("Style enforcement completed successfully.")
    return 0
