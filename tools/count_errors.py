"""Utilities for summarising error occurrences across a repository.

The module provides a small CLI that walks a repository, counts the number of
times the string ``"ERROR"`` appears in the text files it finds, and prints a
summary grouped by file.  It is intentionally lightweight so it can be used in
continuous-integration jobs or as a debugging helper for developers.

Historically the implementation recursed through directories without checking
for symbolic links.  That meant a symlink loop (for example ``a -> .``) could
send the traversal into an infinite recursion or push the scanner outside of
the repository root.  Both behaviours make the command unreliable and could
even result in the tool touching data it is not supposed to.

To keep the traversal robust we aggressively filter symlinks and only yield
paths that resolve underneath the requested root directory.  This guarantees
that callers using ``Path.relative_to`` for formatting receive valid paths and
that the iterator terminates even if it encounters a loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

ERROR_TOKEN = "ERROR"


@dataclass(frozen=True, slots=True)
class FileErrorCount:
    """A lightweight container describing errors found in a file."""

    path: Path
    count: int


def _iter_files(root: Path) -> Iterator[Path]:
    """Yield all files found under *root* while guarding against symlinks.

    The traversal never follows symbolic links.  We keep track of the resolved
    directories we have already processed to avoid repeated work (or loops in
    case symlinks are introduced between traversals).  Each yielded path is
    guaranteed to resolve to a location underneath ``root``.
    """

    root = root.resolve()
    stack: list[Path] = [root]
    visited_dirs: set[Path] = set()

    while stack:
        current = stack.pop()

        # Skip symbolic links outright—they can jump outside the project tree
        # or create loops that would otherwise cause an infinite traversal.
        if current.is_symlink():
            continue

        try:
            resolved = current.resolve()
        except (FileNotFoundError, OSError, RuntimeError):
            # If the file disappeared or cannot be resolved we simply skip it.
            continue

        if not resolved.is_relative_to(root):
            # Guard against directories that resolve outside the repository,
            # such as "../other" or absolute paths reached through symlinks.
            continue

        if resolved.is_dir():
            if resolved in visited_dirs:
                continue
            visited_dirs.add(resolved)

            try:
                entries = sorted(resolved.iterdir(), key=lambda p: p.name)
            except OSError:
                # Skip directories we cannot read.
                continue

            stack.extend(reversed(entries))
            continue

        if resolved.is_file():
            yield resolved


def _count_file_errors(path: Path, token: str = ERROR_TOKEN) -> int:
    """Count the number of occurrences of *token* in *path*.

    The counting is performed line-by-line to keep the memory footprint low
    even for large files.  Files that cannot be decoded using UTF-8 are
    ignored, mirroring the pragmatic behaviour expected for command-line tools.
    """

    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if token in line)
    except (OSError, UnicodeDecodeError):
        return 0


def scan_repository(root: Path, token: str = ERROR_TOKEN) -> list[FileErrorCount]:
    """Return ``FileErrorCount`` entries for files containing *token*.

    ``root`` may be given as either a relative or an absolute path; the search
    is always restricted to files located inside the resolved root directory.
    The resulting list is sorted by the resolved file path to keep the output
    deterministic and straightforward to test.
    """

    root = root.resolve()
    results = [
        FileErrorCount(path=path, count=_count_file_errors(path, token))
        for path in _iter_files(root)
    ]

    return sorted((entry for entry in results if entry.count), key=lambda e: e.path)


def format_report(entries: Iterable[FileErrorCount], root: Path) -> str:
    """Format the collected ``entries`` relative to *root* for display."""

    root = root.resolve()
    lines = []
    for entry in entries:
        try:
            relative = entry.path.relative_to(root)
        except ValueError:
            # Skip entries that unexpectedly fall outside the repository.  The
            # traversal already guards against this, so this is mainly a safety
            # net to keep the formatter resilient against improper use.
            continue
        lines.append(f"{relative}: {entry.count}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Simple command-line interface returning ``0`` for success."""

    import argparse

    parser = argparse.ArgumentParser(description="Summarise error counts.")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        type=Path,
        help="Root directory to scan (defaults to current directory)",
    )
    parser.add_argument(
        "--token",
        default=ERROR_TOKEN,
        help="Substring to look for when counting errors (default: %(default)s)",
    )

    args = parser.parse_args(argv)
    entries = scan_repository(Path(args.root), token=args.token)
    report = format_report(entries, Path(args.root))
    if report:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
