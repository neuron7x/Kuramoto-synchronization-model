#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Markdown link-integrity gate — fail-closed enforcement of internal link health.

Scans every tracked Markdown file (``git ls-files '*.md'``) for links written as

* inline links       ``[text](target)``
* reference-style    ``[label]: target`` definitions

and classifies each *relative* link target as one of:

* ``RESOLVED``      — the target file exists on disk (relative to the linking
  file's directory), OR is an in-document anchor (``#section``);
* ``BROKEN``        — the target is a repo-internal path but the file is missing;
* ``OUTSIDE-ROOT``  — the resolved path escapes the repository root.

Links with a URL scheme (``http:``, ``https:``, ``mailto:``, ``ftp:``, ``tel:``)
are treated as *external* and never checked for on-disk existence.

Anchor fragments (``file.md#section``) are stripped before existence checks;
anchor-level validation (does ``#section`` exist inside the target?) is **out of
scope** for this gate — see ``docs/LINK_POLICY.md``.

Outside-root links are only permitted when explicitly listed in the allowlist
(``docs/link_allowlist.json``) with a human rationale.

Stdlib-only; fast. Mirrors the docs-consistency / claim-boundary gates.

Usage::

    python scripts/ci/check_links.py                 # verify (CI, fail-closed)
    python scripts/ci/check_links.py --json out.json # also write the audit report
    python scripts/ci/check_links.py --root PATH     # scan a different root (tests)

Exit codes::

    0  — zero internal BROKEN links and every OUTSIDE-ROOT link allowlisted
    1  — at least one BROKEN internal link or un-allowlisted OUTSIDE-ROOT link
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Location & policy files
# ---------------------------------------------------------------------------

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_REL = Path("docs") / "link_allowlist.json"

# URL schemes we treat as external (never existence-checked).
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")

# Inline links: [text](target). Target ends at the first unescaped ')' or
# whitespace-introduced optional "title". We intentionally do NOT match image
# links differently — an image with a missing local asset is still a broken link,
# but we scope this gate to *.md targets and other repo paths; non-.md targets
# (images, code files) are still resolved for existence.
#
# The capture stops at whitespace or ')'. A leading '!' (image) is allowed before
# the '[' but is not captured.
_INLINE_RE = re.compile(r"\[(?:[^\]]*)\]\(\s*([^)\s]+)(?:\s+[^)]*)?\)")

# Reference-style definitions:  [label]: target "optional title"
_REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(\S+)")

# Fenced code block delimiters — links inside code fences are not real links.
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# Inline-code spans: strip `...` so we don't parse example links inside them.
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


def list_markdown_files(root: Path) -> list[Path]:
    """Return tracked ``*.md`` files under *root* (falls back to a filesystem walk)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "*.md"],
            capture_output=True,
            text=True,
            check=True,
        )
        rels = [line for line in out.stdout.splitlines() if line.strip()]
        if rels:
            return [root / r for r in rels]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    # Fallback: filesystem walk (used by test fixtures / non-git trees).
    return [p for p in sorted(root.rglob("*.md")) if ".git" not in p.parts]


def is_external(target: str) -> bool:
    """True when *target* carries a URL scheme (http:, mailto:, etc.)."""
    return bool(_SCHEME_RE.match(target))


def extract_links(text: str) -> list[str]:
    """Return raw link targets from Markdown *text*, skipping code fences/spans."""
    targets: list[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        if _FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = _INLINE_CODE_RE.sub("", raw_line)
        ref = _REF_DEF_RE.match(line)
        if ref:
            targets.append(ref.group(1))
            continue
        for m in _INLINE_RE.finditer(line):
            targets.append(m.group(1))
    return targets


def classify(
    target: str, md_file: Path, root: Path
) -> tuple[str, str | None]:
    """Classify a single link *target*.

    Returns ``(status, resolved_relpath_or_None)`` where status is one of
    ``EXTERNAL``, ``ANCHOR``, ``RESOLVED``, ``BROKEN``, ``OUTSIDE-ROOT``.
    """
    if is_external(target):
        return ("EXTERNAL", None)

    # Pure in-document anchor.
    if target.startswith("#"):
        return ("ANCHOR", None)

    # Strip anchor / query fragments before existence resolution.
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    if not path_part:
        # Was just "#..." handled above; empty means nothing to resolve.
        return ("ANCHOR", None)

    # Resolve relative to the linking file's directory.
    base = md_file.parent
    try:
        candidate = (base / path_part).resolve()
        root_res = root.resolve()
    except (OSError, RuntimeError):
        return ("BROKEN", path_part)

    # Outside-root detection (escapes repo root via ../).
    try:
        rel = candidate.relative_to(root_res)
    except ValueError:
        return ("OUTSIDE-ROOT", path_part)

    if candidate.exists():
        return ("RESOLVED", str(rel))
    return ("BROKEN", str(rel))


def load_allowlist(root: Path) -> dict[str, str]:
    """Load outside-root allowlist: ``{ "file.md::../target" : "reason" }``.

    Keys are ``"<md-relpath>::<raw-target>"``. A bare ``"<raw-target>"`` key
    (no ``::``) allowlists that target from any file.
    """
    path = root / ALLOWLIST_REL
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("outside_root_allowlist", data)
    if isinstance(entries, list):
        # list of {"file","target","reason"}
        out: dict[str, str] = {}
        for e in entries:
            key = f"{e.get('file','')}::{e['target']}" if e.get("file") else e["target"]
            out[key] = e.get("reason", "")
        return out
    return dict(entries)


def is_allowlisted(md_rel: str, target: str, allow: dict[str, str]) -> bool:
    return f"{md_rel}::{target}" in allow or target in allow


def scan(root: Path) -> dict:
    """Scan the tree and return a structured audit report."""
    root = root.resolve()
    allow = load_allowlist(root)
    files = list_markdown_files(root)

    per_file: dict[str, dict] = {}
    broken: list[dict] = []
    outside_unallowed: list[dict] = []
    counts = {
        "files_scanned": len(files),
        "links_total": 0,
        "external": 0,
        "anchor": 0,
        "resolved": 0,
        "broken": 0,
        "outside_root": 0,
        "outside_root_allowlisted": 0,
    }

    for md in sorted(files):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        md_rel = str(md.resolve().relative_to(root))
        f_broken: list[str] = []
        f_outside: list[str] = []
        for target in extract_links(text):
            counts["links_total"] += 1
            status, resolved = classify(target, md, root)
            if status == "EXTERNAL":
                counts["external"] += 1
            elif status == "ANCHOR":
                counts["anchor"] += 1
            elif status == "RESOLVED":
                counts["resolved"] += 1
            elif status == "BROKEN":
                counts["broken"] += 1
                f_broken.append(target)
                broken.append({"file": md_rel, "target": target, "resolved": resolved})
            elif status == "OUTSIDE-ROOT":
                counts["outside_root"] += 1
                if is_allowlisted(md_rel, target, allow):
                    counts["outside_root_allowlisted"] += 1
                else:
                    f_outside.append(target)
                    outside_unallowed.append({"file": md_rel, "target": target})
        if f_broken or f_outside:
            per_file[md_rel] = {"broken": f_broken, "outside_root_unallowed": f_outside}

    return {
        "counts": counts,
        "per_file": per_file,
        "broken": broken,
        "outside_root_unallowed": outside_unallowed,
        "internal_broken_total": counts["broken"],
        "outside_root_unallowed_total": len(outside_unallowed),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Markdown link-integrity gate.")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repo root to scan")
    ap.add_argument("--json", type=Path, default=None, help="write audit report to this path")
    ap.add_argument("--quiet", action="store_true", help="suppress the per-link listing")
    args = ap.parse_args(argv)

    report = scan(args.root)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    c = report["counts"]
    broken_n = report["internal_broken_total"]
    outside_n = report["outside_root_unallowed_total"]

    if not args.quiet:
        for item in report["broken"]:
            print(f"BROKEN        {item['file']} -> {item['target']}")
        for item in report["outside_root_unallowed"]:
            print(f"OUTSIDE-ROOT  {item['file']} -> {item['target']} (not allowlisted)")

    print(
        f"[check_links] files={c['files_scanned']} links={c['links_total']} "
        f"resolved={c['resolved']} external={c['external']} anchor={c['anchor']} "
        f"broken={broken_n} outside-root(unallowed)={outside_n} "
        f"outside-root(allowlisted)={c['outside_root_allowlisted']}"
    )

    if broken_n or outside_n:
        print(
            f"[check_links] FAIL: {broken_n} broken internal link(s), "
            f"{outside_n} un-allowlisted outside-root link(s).",
            file=sys.stderr,
        )
        return 1
    print("[check_links] OK: 0 broken internal links; all outside-root links allowlisted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
