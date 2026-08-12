#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""ENV-011 — every documented `make <target>` golden path must be a REAL Makefile target.

First principle (a golden-path command a doc tells you to run must actually exist, or the doc is
a silent lie): READMEs and docs advertise `make ...` commands. Nothing verified they resolve.
This gate parses the Makefile's real targets and scans docs for `make <target>` citations that
appear in a **code context** (inline `` `make x` `` or a fenced ``` block) — NOT English prose
like "make sure" / "make the" — and fails closed if any cited target does not exist.

Prose-vs-command discrimination: only citations inside backticks or fenced code blocks count;
a small stop-list (`sure`, `the`, `it`, `a`, ...) is also filtered as belt-and-suspenders.
An allowlist (`.github/golden_path_allowlist.json`) covers commands defined elsewhere (a
sub-Makefile, a documented external tool).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"
ALLOW = ROOT / ".github" / "golden_path_allowlist.json"
BASELINE = ROOT / ".github" / "golden_path_baseline.json"
DOC_ROOTS = ["README.md", "docs"]
STOP = {"sure", "the", "it", "a", "an", "this", "them", "that", "your", "our", "up", "no",
        "me", "for", "and", "or", "to", "CI"}

RE_TARGET = re.compile(r"^([a-zA-Z][\w-]*):", re.M)
# target token must END in an alphanumeric (drop trailing-hyphen prose fragments like "profile-")
RE_INLINE = re.compile(r"`\s*make\s+([a-zA-Z][\w-]*[a-zA-Z0-9])")   # `make target`
RE_FENCE = re.compile(r"```.*?```", re.S)
RE_MAKE = re.compile(r"\bmake\s+([a-zA-Z][\w-]*[a-zA-Z0-9])")


def _real_targets() -> set[str]:
    return set(RE_TARGET.findall(MAKEFILE.read_text(encoding="utf-8")))


def _cited(md: str) -> set[str]:
    cited: set[str] = set()
    cited.update(RE_INLINE.findall(md))                          # inline code
    for block in RE_FENCE.findall(md):                          # fenced code blocks
        cited.update(RE_MAKE.findall(block))
    return {c for c in cited if c not in STOP}


def _docs() -> list[Path]:
    out: list[Path] = []
    for r in DOC_ROOTS:
        p = ROOT / r
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(p.rglob("*.md"))
    return out


def _dangling() -> tuple[list[str], set[str], int]:
    real = _real_targets()
    allow = set(json.loads(ALLOW.read_text()).get("allow", [])) if ALLOW.exists() else set()
    known = real | allow
    dangling: list[str] = []
    checked = 0
    for doc in _docs():
        for tgt in _cited(doc.read_text(encoding="utf-8", errors="ignore")):
            checked += 1
            if tgt not in known:
                dangling.append(f"{doc.relative_to(ROOT)}::make {tgt}")
    return sorted(set(dangling)), real, checked


def main() -> int:
    if "--write-baseline" in sys.argv:
        current, _, _ = _dangling()
        BASELINE.write_text(json.dumps({
            "_doc": "ENV-011 golden-path ratchet: pre-existing docs that cite a non-existent make "
                    "target. A NEW dangling citation (not here) fails the gate; a baseline entry "
                    "that is now fixed should be removed (tighten). Paydown tracked in "
                    "docs/audit/ENV-011_GOLDEN_PATH_DEBT_2026-07-21.md.",
            "known_dangling": current,
        }, ensure_ascii=False, indent=1) + "\n")
        print(f"wrote baseline: {len(current)} known-dangling golden paths")
        return 0

    dangling, real, checked = _dangling()
    baseline = set(json.loads(BASELINE.read_text()).get("known_dangling", [])) if BASELINE.exists() else set()
    new = [d for d in dangling if d not in baseline]
    fixed = [b for b in baseline if b not in set(dangling)]

    if new:
        print(f"[-] golden-path gate RED: {len(new)} NEW documented `make` command(s) that do not "
              f"resolve to a real Makefile target (ratchet vs {len(baseline)} baselined):", file=sys.stderr)
        for d in new:
            doc, tgt = d.split("::make ", 1)
            print(f"    {doc} cites `make {tgt}` — no such target", file=sys.stderr)
        print("    Fix the doc to cite a real target, add the target, or (external cmd) allowlist "
              "in .github/golden_path_allowlist.json.", file=sys.stderr)
        return 1
    if fixed:
        print(f"[-] golden-path gate RED: {len(fixed)} baselined dangling path(s) are now FIXED — "
              f"tighten the baseline (run --write-baseline):", file=sys.stderr)
        for f in fixed:
            print(f"    resolved: {f}", file=sys.stderr)
        return 1
    print(f"[+] golden-path gate GREEN: no NEW dangling `make` citation "
          f"({len(real)} real targets; {checked} checked; {len(baseline)} legacy baselined for paydown).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
