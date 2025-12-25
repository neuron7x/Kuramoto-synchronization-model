"""Static lint checks for TradePulse documentation assets."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Protocol, Sequence

DEFAULT_TARGETS: tuple[Path, ...] = (
    Path("docs"),
    Path("README.md"),
)
MARKDOWN_SUFFIXES: tuple[str, ...] = (".md", ".markdown")
SKIP_DIR_NAMES: frozenset[str] = frozenset({".git", "node_modules", "__pycache__"})


@dataclass(slots=True)
class LintIssue:
    """Represents a single documentation lint failure."""

    path: Path
    line: int
    message: str
    rule: str

    def format(self, root: Path | None = None) -> str:
        prefix = self.path
        if root is not None:
            try:
                prefix = self.path.relative_to(root)
            except ValueError:
                prefix = self.path
        return f"{prefix}:{self.line}: {self.message} [{self.rule}]"


class LintRule(Protocol):
    """Protocol describing a single documentation lint rule."""

    name: str
    description: str

    def check(self, path: Path, lines: Sequence[str]) -> Iterable[LintIssue]: ...


class HeadingFirstRule:
    name = "heading-first"
    description = "Require a top-level heading (or YAML front matter followed by one)."

    def check(self, path: Path, lines: Sequence[str]) -> Iterable[LintIssue]:
        in_front_matter = False
        in_html_comment = False
        in_html_block = 0  # Depth counter for nested HTML elements
        for index, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            if index == 0 and stripped == "---":
                in_front_matter = True
                continue
            if in_front_matter:
                if stripped == "---":
                    in_front_matter = False
                continue
            # Handle HTML comments
            # Check for single-line comment first (e.g., <!-- comment -->)
            if stripped.startswith("<!--") and stripped.endswith("-->"):
                continue
            # Handle multi-line HTML comments
            if stripped.startswith("<!--"):
                in_html_comment = True
                continue
            if in_html_comment:
                if stripped.endswith("-->"):
                    in_html_comment = False
                continue
            # Handle HTML block elements (e.g., <div>, <picture>, <p>, etc.)
            # These are allowed before the heading for styling purposes.
            # We use a simple depth counter to track nested elements.
            if stripped.startswith("<") and not stripped.startswith("<!"):
                # Self-closing tags: <img />, <br/>, etc. - don't change block state
                if "/>" in stripped:
                    continue
                # Closing tags decrease block depth
                if stripped.startswith("</"):
                    in_html_block = max(0, in_html_block - 1)
                else:
                    # Opening tags increase block depth
                    in_html_block += 1
                continue
            if in_html_block > 0:
                # Stay in HTML block until depth returns to 0
                continue
            if not stripped:
                continue
            if stripped.startswith("# "):
                return []
            return [
                LintIssue(
                    path=path,
                    line=index + 1,
                    message="first content line must be a level-1 heading",
                    rule=self.name,
                )
            ]
        return [
            LintIssue(
                path=path,
                line=1,
                message="first content line must be a level-1 heading",
                rule=self.name,
            )
        ]


class TrailingWhitespaceRule:
    name = "trailing-whitespace"
    description = "Disallow trailing whitespace in Markdown documents."

    def check(self, path: Path, lines: Sequence[str]) -> Iterable[LintIssue]:
        for index, raw_line in enumerate(lines):
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue

            trimmed = line.rstrip(" \t")
            if trimmed == line:
                continue

            trailing_segment = line[len(trimmed) :]
            if trailing_segment == "  ":
                # Allow Markdown hard line breaks signified by exactly two spaces.
                continue

            yield LintIssue(
                path=path,
                line=index + 1,
                message="remove trailing whitespace",
                rule=self.name,
            )


class TabCharacterRule:
    name = "no-tabs"
    description = "Tabs often render inconsistently; prefer spaces in documentation."

    def check(self, path: Path, lines: Sequence[str]) -> Iterable[LintIssue]:
        for index, raw_line in enumerate(lines):
            if "\t" in raw_line:
                yield LintIssue(
                    path=path,
                    line=index + 1,
                    message="replace tab characters with spaces",
                    rule=self.name,
                )


class ForbiddenPhraseRule:
    name = "forbidden-phrases"
    description = "Prevent placeholders such as TODO or TBD from shipping."

    _PATTERN = re.compile(r"\b(TODO|FIXME|TBD)\b", re.IGNORECASE)

    def check(self, path: Path, lines: Sequence[str]) -> Iterable[LintIssue]:
        in_fenced_block = False
        for index, raw_line in enumerate(lines):
            stripped = raw_line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fenced_block = not in_fenced_block
                continue

            if in_fenced_block:
                continue

            cleaned = re.sub(r"`[^`]*`", "", raw_line)
            match = self._PATTERN.search(cleaned)
            if match:
                token = match.group(1).upper()
                yield LintIssue(
                    path=path,
                    line=index + 1,
                    message=f"remove placeholder token '{token}'",
                    rule=self.name,
                )


DEFAULT_RULES: tuple[LintRule, ...] = (
    HeadingFirstRule(),
    TrailingWhitespaceRule(),
    TabCharacterRule(),
    ForbiddenPhraseRule(),
)


def _is_markdown_file(path: Path) -> bool:
    return path.suffix.lower() in MARKDOWN_SUFFIXES and path.is_file()


def _iter_markdown_files(targets: Sequence[Path]) -> list[Path]:
    discovered: list[Path] = []
    for target in targets:
        if not target.exists():
            continue
        if target.is_file():
            if _is_markdown_file(target):
                discovered.append(target.resolve())
            continue
        for root, dirs, files in os.walk(target):
            dirs[:] = [name for name in dirs if name not in SKIP_DIR_NAMES]
            for file in files:
                candidate = Path(root) / file
                if _is_markdown_file(candidate):
                    discovered.append(candidate.resolve())
    return sorted({path for path in discovered})


def lint_paths(
    targets: Sequence[Path], rules: Sequence[LintRule] = DEFAULT_RULES
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for path in _iter_markdown_files(targets):
        content = path.read_text(encoding="utf-8").splitlines()
        for rule in rules:
            issues.extend(rule.check(path, content))
    return sorted(issues, key=lambda issue: (issue.path, issue.line, issue.rule))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=DEFAULT_TARGETS,
        help="Files or directories containing Markdown documentation to lint.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Do not fail if a provided path does not exist.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    targets: List[Path] = []
    missing: list[Path] = []
    for candidate in args.paths:
        if candidate.exists():
            targets.append(candidate)
        else:
            missing.append(candidate)

    if missing and not args.allow_missing:
        parser.error(
            f"Path '{missing[0]}' does not exist. Use --allow-missing to skip."
        )

    if not targets:
        if args.allow_missing:
            print("No valid documentation paths supplied; skipping (--allow-missing).")
            return 0
        parser.error("No valid documentation paths supplied.")

    issues = lint_paths(targets)

    if issues:
        for issue in issues:
            print(issue.format(root=Path.cwd()))
        print(f"\nDocumentation lint failed with {len(issues)} issue(s).")
        return 1

    files = _iter_markdown_files(targets)
    print(f"Documentation lint passed for {len(files)} file(s).")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
