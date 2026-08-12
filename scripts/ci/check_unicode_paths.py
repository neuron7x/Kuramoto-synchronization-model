#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate for Unicode (non-ASCII) tracked path portability.

Audit finding #1: the repository tracks a Cyrillic-named document
(``docs/operations/СТАН_РОЗВИТКУ_ПРОЄКТУ.md``). ``git archive`` -> zip stores
the UTF-8 bytes correctly and sets the zip "language encoding" flag (general
purpose bit 11, ``0x800``), so any UTF-8-aware extractor (Python ``zipfile``,
``bsdtar``, ``unzip`` built with UTF-8 support) reproduces the exact name. Some
legacy ``unzip`` builds ignore that flag and render the octets as ``#U....``.
That is a *display* defect in the extractor, not a corruption of the archived
bytes.

The genuine portability hazard is a tracked name stored in NFD (decomposed)
form: NFC and NFD render identically but are different byte sequences, and a
macOS-authored path can round-trip to a byte sequence Linux tooling and internal
Markdown links do not match. This gate therefore enforces, fail-closed, that
EVERY tracked non-ASCII path is:

  1. NFC-normalized  (``unicodedata.normalize('NFC', name) == name``),
  2. resolvable on disk (the working-tree file exists),
  3. byte-identical after a ``git archive --format=zip HEAD`` round-trip, and
  4. free of broken internal references: any other tracked Markdown file that
     mentions the path as a repo-relative token must point at an existing file.

Polarity (standard ``check_*`` convention: exit 0 == clean):

    exit 0  -> every non-ASCII tracked path is NFC, resolvable, survives the
               archive round-trip byte-identical, and every internal reference
               to it resolves.
    exit 1  -> at least one violation (NFD name, missing file, byte drift in the
               archive, or a broken internal reference). Fail-closed.
    exit 2  -> usage / IO / environment error (e.g. not a git tree).

Usage:
    python scripts/ci/check_unicode_paths.py
"""

from __future__ import annotations

import io
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Suffixes that mark a backtick/inline token as a concrete repository path when
# scanning Markdown for internal references.
_REF_SUFFIXES: tuple[str, ...] = (".md", ".py", ".json", ".txt", ".yaml", ".yml")


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        check=False,
    )


def tracked_paths() -> list[str]:
    """Return every tracked path, decoded as UTF-8 (quotePath disabled)."""
    cp = _git("-c", "core.quotePath=false", "ls-files", "-z")
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", "replace"))
    return [p for p in cp.stdout.decode("utf-8").split("\0") if p]


def non_ascii(paths: list[str]) -> list[str]:
    return [p for p in paths if any(ord(c) > 0x7F for c in p)]


def archive_names() -> set[str]:
    """Names inside ``git archive --format=zip HEAD``, decoded honoring UTF-8."""
    cp = _git("archive", "--format=zip", "HEAD")
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", "replace"))
    zf = zipfile.ZipFile(io.BytesIO(cp.stdout))
    names: set[str] = set()
    for info in zf.infolist():
        # zipfile decodes cp437 when the UTF-8 flag is absent; re-encode to
        # recover the true bytes, then decode as UTF-8 for the comparison.
        if info.flag_bits & 0x800:
            names.add(info.filename)
        else:
            names.add(info.filename.encode("cp437").decode("utf-8", "replace"))
    return names


def internal_reference_violations(paths: list[str], targets: list[str]) -> list[str]:
    """Find tracked Markdown files that name a non-ASCII target that is missing.

    A "reference" is any occurrence of the exact repo-relative target string
    inside a tracked ``.md`` file (backtick code-span or Markdown link). The
    reference is a violation only when the referenced path does NOT exist on
    disk -- i.e. a link that cannot resolve.
    """
    violations: list[str] = []
    md_files = [p for p in paths if p.endswith(".md")]
    on_disk = {p for p in targets if (ROOT / p).exists()}
    for target in targets:
        for md in md_files:
            try:
                text = (ROOT / md).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if target in text and target not in on_disk:
                violations.append(f"{md} references missing path '{target}'")
    return violations


def main() -> int:
    try:
        paths = tracked_paths()
    except (RuntimeError, OSError) as exc:  # pragma: no cover - environment
        print(f"UNICODE-PATHS: environment error: {exc}", file=sys.stderr)
        return 2

    targets = non_ascii(paths)
    if not targets:
        print("UNICODE-PATHS: PASS — no non-ASCII tracked paths.")
        return 0

    try:
        arc = archive_names()
    except (RuntimeError, OSError) as exc:  # pragma: no cover - environment
        print(f"UNICODE-PATHS: environment error: {exc}", file=sys.stderr)
        return 2

    violations: list[str] = []
    for p in targets:
        nfc = unicodedata.normalize("NFC", p)
        if p != nfc:
            violations.append(
                f"NON-NFC tracked path '{p}' (NFC would be '{nfc}'); "
                "decomposed names are a portability hazard"
            )
        if not (ROOT / p).exists():
            violations.append(f"tracked non-ASCII path '{p}' is missing on disk")
        if p not in arc:
            violations.append(
                f"tracked non-ASCII path '{p}' did not survive git-archive "
                "round-trip byte-identical"
            )

    violations.extend(internal_reference_violations(paths, targets))

    if violations:
        print("UNICODE-PATHS: FAIL — portability violations:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print(
        f"UNICODE-PATHS: PASS — {len(targets)} non-ASCII tracked path(s) are "
        "NFC-normalized, resolvable, archive-stable, and referenced without "
        "broken links."
    )
    for p in targets:
        print(f"  ok: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
