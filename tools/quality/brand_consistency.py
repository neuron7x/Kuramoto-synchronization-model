# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Brand-consistency guard for the GeoSync repository.

This is a **permanent regression barrier** that prevents any future commit
from reintroducing legacy brand identifiers that the April 2026 rebrand
removed. It runs in CI on every PR and every push to ``main``. A
non-zero exit means the working tree contains a forbidden token in
either file content, a filename, or a directory name.

Design goals
------------
- **Zero dependencies.** Pure standard library; runs under Python 3.11 and
  newer. If this script needs a package to run, the gate itself becomes a
  regression risk.
- **Deterministic.** Output is sorted, stable across runs, stable across
  filesystems. Two CI invocations on the same commit produce byte-for-byte
  identical reports.
- **Allowlist-aware.** A TOML allowlist at
  ``configs/quality/brand_allowlist.toml`` grandfathers individual
  legacy references that must remain (e.g. historical notes in CHANGELOG
  or cross-references to the KURAMOTO_NETWORK_ENGINE_METHODOLOGY.md
  source paper). Entries are matched by ``(path, token)`` pair; every
  grandfathered hit requires an explicit ``reason``.
- **Fast.** Walks the repo once, reads each candidate file once, uses
  ``bytes``-level search to avoid decoding non-text files.

Exit codes
----------
- ``0`` — clean repo, no violations outside the allowlist.
- ``1`` — at least one violation. The report is printed to stdout (or
  emitted as JSON when ``--json`` is passed).
- ``2`` — internal error (bad allowlist, unreadable config, etc.).

Usage
-----
::

    # Human-readable report
    python tools/quality/brand_consistency.py

    # Machine-readable JSON for CI integration
    python tools/quality/brand_consistency.py --json

    # Point at a different repo root
    python tools/quality/brand_consistency.py --root /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

__all__ = [
    "FORBIDDEN_TOKENS",
    "Violation",
    "Report",
    "scan_repo",
    "load_allowlist",
    "main",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Legacy brand tokens that must never reappear. Matched case-insensitively
#: via the word-boundary regex below. Every token here is a **distinct**
#: legacy identifier — we deliberately list the casing variants explicitly
#: so that future audits can diff this constant against the rebrand commit
#: message without cross-referencing a regex compiler.
FORBIDDEN_TOKENS: tuple[str, ...] = (
    "TradePulse",
    "tradepulse",
    "trade_pulse",
    "TRADEPULSE",
    "HydroBrain",
    "hydrobrain",
    "hydro_brain",
    "HYDROBRAIN",
    "HydroFlow",
    "NeurotradePro",
    "neurotradepro",
    "neurotrade_pro",
    "NeuroTrade",  # catches "NeuroTrade Pro" in docstrings
    "NeuroPro",  # matched as whole word below, won't hit "NeuroProductivity"
)

#: Directory names to skip entirely — build artifacts, caches, third-party
#: trees, and historical archives that are deliberately frozen with legacy
#: references for provenance.
SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".env",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".next",
        "htmlcov",
        "coverage",
        ".coverage",
        ".tox",
        "legacy",  # historical code frozen with legacy names on purpose
    }
)

#: Parent directories whose contents we skip by path prefix (relative to
#: the repo root). Different from ``SKIP_DIRS`` because we want
#: ``docs/archive`` skipped but not *every* directory named ``archive``.
SKIP_PREFIXES: tuple[str, ...] = (
    "docs/archive",
    "artifacts",
    "observability/audit",
    ".claude/archive",  # rebrand provenance ledgers — must keep legacy names
    ".claude/worktrees",  # ephemeral Claude Code agent worktrees, not repo source
    "tests/archive",  # tests that exercise the archive ledger schemas
    "tools/archive",  # tooling that compares old-repo to new-repo by name
)

#: File extensions we scan for content. Everything else is skipped on the
#: content pass (but the filename pass still runs).
TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".md",
        ".rst",
        ".txt",
        ".yml",
        ".yaml",
        ".toml",
        ".ini",
        ".cfg",
        ".json",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".sh",
        ".bash",
        ".zsh",
        ".env.example",
        ".editorconfig",
        ".html",
        ".css",
        ".scss",
        ".nvmrc",
        ".dockerignore",
        ".gitignore",
    }
)

#: Filenames that have no extension but are still text (Dockerfile, Makefile).
TEXT_STEMS: frozenset[str] = frozenset(
    {"Dockerfile", "Makefile", "CODEOWNERS", "LICENSE", "README"}
)

#: Size cap for content scanning. Files above this are reported to stderr
#: but not read (a legitimate text file rarely exceeds 1 MB, and we do not
#: want to OOM CI on a checked-in binary blob disguised with a text
#: extension).
MAX_FILE_BYTES: int = 1_024 * 1_024  # 1 MB


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AllowlistEntry:
    """A grandfathered legacy reference.

    Matching is exact on the tuple ``(path, token)``; ``reason`` is free
    text rendered in the report to explain why the exception exists.
    """

    path: str
    token: str
    reason: str


@dataclass(frozen=True, slots=True, order=True)
class Violation:
    """A single legacy-token hit detected by :func:`scan_repo`.

    Instances are totally ordered by their fields so reports are
    deterministic. The ``kind`` discriminator is the string
    ``"content"`` for content matches, ``"filename"`` for filename
    matches, or ``"dirname"`` for directory-name matches.
    """

    path: str
    line: int
    column: int
    token: str
    kind: str
    context: str = ""


@dataclass(slots=True)
class Report:
    """Aggregate scan result."""

    violations: list[Violation] = field(default_factory=list)
    scanned_files: int = 0
    skipped_files: int = 0
    allowlist_hits: int = 0

    @property
    def clean(self) -> bool:
        """``True`` iff no violations remain after allowlist filtering."""
        return not self.violations


# ---------------------------------------------------------------------------
# Allowlist loading
# ---------------------------------------------------------------------------


def load_allowlist(path: Path) -> list[AllowlistEntry]:
    """Parse ``configs/quality/brand_allowlist.toml``.

    Returns an empty list if the file does not exist — the allowlist is
    optional and only useful for grandfathered exceptions. The TOML
    schema is::

        [[allow]]
        path = "CHANGELOG.md"
        token = "TradePulse"
        reason = "historical rebrand note"
    """
    if not path.exists():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"failed to read allowlist {path}: {exc}") from exc
    raw_entries = data.get("allow", [])
    if not isinstance(raw_entries, list):
        raise ValueError(f"{path}: 'allow' must be an array of tables")
    out: list[AllowlistEntry] = []
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: allow[{i}] must be a table")
        missing = {"path", "token", "reason"} - set(raw)
        if missing:
            raise ValueError(f"{path}: allow[{i}] missing fields: {sorted(missing)}")
        out.append(
            AllowlistEntry(
                path=str(raw["path"]),
                token=str(raw["token"]),
                reason=str(raw["reason"]),
            )
        )
    return out


def _is_allowlisted(violation: Violation, allowlist: Iterable[AllowlistEntry]) -> bool:
    """Return ``True`` if the violation matches any allowlist entry."""
    for entry in allowlist:
        if entry.path == violation.path and entry.token.lower() == violation.token.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Scanning primitives
# ---------------------------------------------------------------------------


def _token_pattern(tokens: Iterable[str]) -> re.Pattern[bytes]:
    """Build a single case-insensitive substring regex over every token.

    Rationale for plain substring matching (instead of ``\\b``-anchored):
    Python identifiers and filenames use ``_`` as the primary separator,
    and the regex engine treats underscore as a *word character*. A
    ``\\b``-anchored pattern therefore **fails** to match ``trade_pulse``
    inside ``neuro_trade_pulse.py`` — exactly the residue shape this
    guard exists to catch. Substring matching catches every compound
    identifier at the cost of occasionally flagging legitimate words
    such as ``NeuroProductivity``; those are handled by explicit
    allowlist entries in ``configs/quality/brand_allowlist.toml``.

    The scan runs against ``bytes`` rather than decoded text so we do
    not pay a UTF-8 decoding cost on every file and we stay robust to
    the odd legacy blob with mixed encoding.
    """
    escaped = [re.escape(t).encode("utf-8") for t in tokens]
    pattern = b"(?:" + b"|".join(escaped) + b")"
    return re.compile(pattern, re.IGNORECASE)


def _is_text_file(path: Path) -> bool:
    """Decide whether ``path`` should be scanned for content."""
    if path.name in TEXT_STEMS:
        return True
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    # Compound suffixes like ``.env.example``
    if path.suffixes and "".join(path.suffixes).lower() in TEXT_EXTENSIONS:
        return True
    return False


def _should_skip_dir(rel: Path) -> bool:
    """Return ``True`` if ``rel`` sits under a skipped directory."""
    parts = rel.parts
    if any(part in SKIP_DIRS for part in parts):
        return True
    rel_str = rel.as_posix()
    if any(rel_str == p or rel_str.startswith(p + "/") for p in SKIP_PREFIXES):
        return True
    # *.egg-info
    if any(part.endswith(".egg-info") for part in parts):
        return True
    return False


def _scan_file_content(path: Path, rel: Path, pattern: re.Pattern[bytes]) -> Iterator[Violation]:
    """Yield one :class:`Violation` per in-file hit."""
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size > MAX_FILE_BYTES:
        print(
            f"brand-consistency: skipping {rel} ({size} bytes > {MAX_FILE_BYTES})",
            file=sys.stderr,
        )
        return
    try:
        blob = path.read_bytes()
    except OSError:
        return
    # Detect binary blobs cheaply: if the first KB has a NUL byte, skip.
    sniff = blob[:1024]
    if b"\x00" in sniff:
        return
    for match in pattern.finditer(blob):
        start = match.start()
        # Line + column — cheap to compute from the byte offset
        line = blob.count(b"\n", 0, start) + 1
        last_newline = blob.rfind(b"\n", 0, start)
        column = start - last_newline if last_newline >= 0 else start + 1
        line_end = blob.find(b"\n", start)
        if line_end == -1:
            line_end = len(blob)
        context = blob[last_newline + 1 : line_end].decode("utf-8", errors="replace").rstrip()
        token = match.group(0).decode("utf-8", errors="replace")
        yield Violation(
            path=rel.as_posix(),
            line=line,
            column=column,
            token=token,
            kind="content",
            context=context[:200],
        )


def _scan_name(rel: Path, is_dir: bool, pattern: re.Pattern[bytes]) -> Iterator[Violation]:
    """Yield violations for file/directory names."""
    name = rel.name.encode("utf-8")
    for match in pattern.finditer(name):
        yield Violation(
            path=rel.as_posix(),
            line=0,
            column=match.start() + 1,
            token=match.group(0).decode("utf-8", errors="replace"),
            kind="dirname" if is_dir else "filename",
            context=rel.name,
        )


# ---------------------------------------------------------------------------
# Top-level scan
# ---------------------------------------------------------------------------


def scan_repo(
    root: Path,
    *,
    allowlist: Iterable[AllowlistEntry] | None = None,
    tokens: Iterable[str] = FORBIDDEN_TOKENS,
) -> Report:
    """Walk ``root`` and return an aggregated :class:`Report`.

    Every file's name is checked; only text files are also scanned for
    content. Entries matched by ``allowlist`` are omitted from the
    report's ``violations`` list but counted in ``allowlist_hits``.
    """
    pattern = _token_pattern(tokens)
    allow_list = list(allowlist or [])
    report = Report()

    # rglob guarantees stable ordering when combined with sorted(). We sort
    # once at the end for a deterministic report, so we only use rglob here
    # as the walker.
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if _should_skip_dir(rel):
            continue
        is_dir = path.is_dir()
        # Scan the name of every file *and* directory.
        for viol in _scan_name(rel, is_dir, pattern):
            if _is_allowlisted(viol, allow_list):
                report.allowlist_hits += 1
                continue
            report.violations.append(viol)
        if is_dir:
            continue
        if not _is_text_file(path):
            report.skipped_files += 1
            continue
        report.scanned_files += 1
        for viol in _scan_file_content(path, rel, pattern):
            if _is_allowlisted(viol, allow_list):
                report.allowlist_hits += 1
                continue
            report.violations.append(viol)

    report.violations.sort()
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_human_report(report: Report) -> str:
    """Render a human-readable report to a string."""
    if report.clean:
        return (
            f"✓ brand-consistency: clean "
            f"({report.scanned_files} files scanned, "
            f"{report.allowlist_hits} allowlisted)\n"
        )
    lines: list[str] = []
    lines.append(
        f"✗ brand-consistency: {len(report.violations)} violation(s) "
        f"across {report.scanned_files} scanned files"
    )
    if report.allowlist_hits:
        lines.append(f"  ({report.allowlist_hits} additional hit(s) allowlisted)")
    lines.append("")
    # Group by path for readability
    by_path: dict[str, list[Violation]] = {}
    for v in report.violations:
        by_path.setdefault(v.path, []).append(v)
    for path in sorted(by_path):
        lines.append(f"  {path}")
        for v in by_path[path]:
            loc = f"{v.line}:{v.column}" if v.line else "name"
            ctx = f" — {v.context}" if v.context else ""
            lines.append(f"    [{v.kind:8s}] {loc:>9s}  {v.token!r}{ctx}")
        lines.append("")
    lines.append(
        "Add an allowlist entry in configs/quality/brand_allowlist.toml "
        "only if the reference must be preserved for historical reasons."
    )
    return "\n".join(lines) + "\n"


def _format_json_report(report: Report) -> str:
    payload = {
        "clean": report.clean,
        "scanned_files": report.scanned_files,
        "skipped_files": report.skipped_files,
        "allowlist_hits": report.allowlist_hits,
        "violations": [asdict(v) for v in report.violations],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog="brand-consistency",
        description=(
            "Fail if the repo contains legacy brand identifiers outside "
            "the configs/quality/brand_allowlist.toml grandfather list."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="Override allowlist path (default: <root>/configs/quality/brand_allowlist.toml).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report instead of the human one.",
    )
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    allowlist_path: Path = (
        args.allowlist.resolve()
        if args.allowlist is not None
        else root / "configs" / "quality" / "brand_allowlist.toml"
    )
    try:
        allowlist = load_allowlist(allowlist_path)
    except ValueError as exc:
        print(f"brand-consistency: {exc}", file=sys.stderr)
        return 2

    report = scan_repo(root, allowlist=allowlist)
    if args.json:
        sys.stdout.write(_format_json_report(report))
    else:
        sys.stdout.write(_format_human_report(report))
    return 0 if report.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
