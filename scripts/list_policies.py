"""Utility to enumerate policy classes defined across the repository.

This script performs a static analysis pass over Python sources in the
repository to locate class definitions whose names end with ``Policy``.
The resulting inventory helps to understand where risk, retry, retention,
and other policy constructs live across the code base.

Usage:
    $ python scripts/list_policies.py [ROOT]

When ``ROOT`` is omitted the repository root (two levels up from this file)
will be used.  The script prints a Markdown-friendly table to ``stdout`` so
that the output can be pasted directly into documentation when needed.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

# Directories that should be ignored when walking the tree.  These either
# contain generated artefacts, third-party code, or build outputs that are
# not part of the first-party Python surface area we want to inspect.
_EXCLUDED_DIRECTORIES: Sequence[str] = (
    ".git",
    "__pycache__",
    ".mypy_cache",
    "build",
    "dist",
    "node_modules",
    "venv",
    ".venv",
)


@dataclass(frozen=True)
class PolicyDefinition:
    """Structured description of a policy class."""

    module: str
    class_name: str
    bases: tuple[str, ...]
    docstring: str | None

    @property
    def fqname(self) -> str:
        """Return the fully-qualified name of the policy class."""

        return f"{self.module}.{self.class_name}"


def iter_python_files(root: Path) -> Iterator[Path]:
    """Yield candidate Python files under ``root`` for inspection.

    The walk is performed using ``Path.rglob`` and filtered to exclude
    directories listed in :data:`_EXCLUDED_DIRECTORIES` to prevent scanning
    vendored or generated content.
    """

    for path in root.rglob("*.py"):
        if any(part in _EXCLUDED_DIRECTORIES for part in path.parts):
            continue
        yield path


class _PolicyVisitor(ast.NodeVisitor):
    """AST visitor that extracts policy class definitions."""

    def __init__(self, module: str, *, definitions: list[PolicyDefinition]) -> None:
        self._module = module
        self._definitions = definitions

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: D401 - inherited doc
        if node.name.endswith("Policy"):
            bases = tuple(_render_base(base) for base in node.bases)
            doc = ast.get_docstring(node)
            self._definitions.append(
                PolicyDefinition(
                    module=self._module,
                    class_name=node.name,
                    bases=bases,
                    docstring=_normalise_docstring(doc),
                )
            )
        self.generic_visit(node)


def _render_base(node: ast.expr) -> str:
    """Render a human-readable representation of a base class expression."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_render_base(node.value)}.{node.attr}"
    if isinstance(node, ast.Subscript):
        return f"{_render_base(node.value)}[{_render_base(node.slice)}]"
    if isinstance(node, ast.Index):  # pragma: no cover - Python <3.9 compatibility
        return _render_base(node.value)
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Tuple):
        return ", ".join(_render_base(elt) for elt in node.elts)
    return ast.unparse(node)


def _normalise_docstring(doc: str | None) -> str | None:
    if doc is None:
        return None
    stripped = doc.strip().splitlines()
    return stripped[0] if stripped else None


def discover_policies(root: Path) -> list[PolicyDefinition]:
    """Collect all policy class definitions under ``root``."""

    definitions: list[PolicyDefinition] = []
    for path in iter_python_files(root):
        module = _module_name(root, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - surfaces to the user
            raise RuntimeError(f"Failed to parse {path}: {exc}") from exc
        visitor = _PolicyVisitor(module, definitions=definitions)
        visitor.visit(tree)
    return sorted(definitions, key=lambda d: (d.module, d.class_name))


def _module_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    return relative.with_suffix("").as_posix().replace("/", ".")


def _format_table(definitions: Iterable[PolicyDefinition]) -> str:
    """Build a Markdown table summarising the discovered policies."""

    header = "| Policy | Bases | Summary |\n| --- | --- | --- |"
    rows = [
        f"| `{definition.fqname}` | {_format_bases(definition.bases)} |"
        f" {definition.docstring or ''} |"
        for definition in definitions
    ]
    return "\n".join((header, *rows)) if rows else "No policy classes found."


def _format_bases(bases: Sequence[str]) -> str:
    if not bases:
        return "(none)"
    return ", ".join(f"`{base}`" for base in bases)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Root directory to scan (defaults to the repository root).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = parse_args(argv)
    root = namespace.root.resolve()
    definitions = discover_policies(root)
    print(_format_table(definitions))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
