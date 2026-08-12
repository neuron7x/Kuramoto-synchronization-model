# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Markdown link resolver — detects broken intra-repo references in docs.

Scans every ``.md`` file under the repository root (excluding ``.git``,
``.venv``, ``.claude/worktrees``, ``.mypy_cache``, ``node_modules``,
``vendor``, ``newsfragments``) and resolves every relative markdown link
target. Reports every link whose target does not exist.

External links (``http://``, ``https://``, ``mailto:``, ``ftp://``) are
ignored. Anchors-only (``#section``) are ignored.
``../path``-style links resolve relative to the file containing them.
``/abs/path``-style links resolve relative to the repository root.

Usage::

    python tools/check_doc_paths.py            # scan + report broken
    python tools/check_doc_paths.py --json     # JSON output for CI

Exit codes:
    0 — no broken links found
    1 — one or more broken links found
    2 — repo not detected
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Markdown link patterns: [text](target) and [text]: target
INLINE = re.compile(r"\[(?:[^\]]*)\]\(\s*<?([^)>\s]+)>?\s*(?:\s+\"[^\"]*\")?\s*\)")
REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*<?([^>\s]+)>?", re.MULTILINE)
EXTERNAL = re.compile(r"^(?:https?:|mailto:|ftp:|tel:|//)", re.IGNORECASE)
EXCLUDE_DIR_PARTS = {
    ".git",
    ".venv",
    ".claude",
    ".mypy_cache",
    "node_modules",
    "vendor",
    "newsfragments",
    ".cache",
}


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        sys.stderr.write("error: not inside a git repository\n")
        sys.exit(2)
    return Path(out.stdout.strip())


def iter_md_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for p in root.rglob("*.md"):
        if any(part in EXCLUDE_DIR_PARTS for part in p.relative_to(root).parts):
            continue
        found.append(p)
    return sorted(found)


def extract_targets(text: str) -> list[str]:
    targets: list[str] = []
    targets.extend(INLINE.findall(text))
    targets.extend(REFERENCE.findall(text))
    return targets


def is_external(target: str) -> bool:
    if EXTERNAL.match(target):
        return True
    if target.startswith("#"):
        return True
    return False


def resolve(target: str, doc: Path, root: Path) -> Path | None:
    """Resolve a markdown link target to a filesystem path; return None if external/anchor."""
    if is_external(target):
        return None
    target = target.split("#", 1)[0]
    target = target.split("?", 1)[0]
    if not target:
        return None
    if target.startswith("/"):
        return root / target.lstrip("/")
    return (doc.parent / target).resolve()


def scan(root: Path) -> dict[str, Any]:
    broken: list[dict[str, Any]] = []
    md_files = iter_md_files(root)
    total_links = 0
    for doc in md_files:
        try:
            text = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for target in extract_targets(text):
            resolved = resolve(target, doc, root)
            if resolved is None:
                continue
            total_links += 1
            if not resolved.exists():
                broken.append(
                    {
                        "doc": str(doc.relative_to(root)),
                        "target": target,
                        "resolved_to": str(resolved),
                    }
                )
    return {
        "files_scanned": len(md_files),
        "links_resolved": total_links,
        "broken_count": len(broken),
        "broken": broken,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect broken markdown links in docs.")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of human report")
    args = parser.parse_args()

    root = repo_root()
    result = scan(root)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["broken_count"] == 0 else 1

    print("===================================================")
    print(f"  Markdown link audit — repo: {root.name}")
    print("===================================================")
    print(f"  Files scanned:     {result['files_scanned']}")
    print(f"  Internal links:    {result['links_resolved']}")
    print(f"  Broken targets:    {result['broken_count']}")
    print()
    if result["broken_count"] == 0:
        print("  ✓ no broken intra-repo links")
        return 0
    print("  Broken links (path → target):")
    for entry in result["broken"][:200]:
        print(f"    {entry['doc']}")
        print(f"        → {entry['target']}")
    if result["broken_count"] > 200:
        print(f"    … and {result['broken_count'] - 200} more")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
