#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""SEC-016 — security regression corpus (fail-closed gate).

Seeded from the SEC-010 attack-surface review. It ratchets the dangerous-primitive surface so a
NEW instance cannot slip in silently: the review established the *current* safe baseline, this
gate keeps it. Fails closed (RED) when first-party code introduces:

  * ``os.system(``                          — never allowed (use subprocess list-argv)
  * unsafe ``yaml.load(`` (not safe_load, no SafeLoader) — YAML code-exec
  * a NEW ``shell=True`` site not in the allowlist — shell injection surface
  * a NEW ``pickle.load``/``Unpickler(...).load()`` site not in the allowlist — deserialize RCE

The allowlist (``.github/security_regression_allowlist.json``) records the KNOWN, reviewed sites
(the 2 committed-config ``shell=True`` runners and the 2 restricted-unpickler loads). A site that
disappears is fine (surface shrank); a NEW one is a regression → RED.

Scope: first-party source only (excludes tests/, .git/, vendored/build dirs). Pure stdlib.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOW = ROOT / ".github" / "security_regression_allowlist.json"
FIRST_PARTY = ["geosync", "core", "execution", "runtime", "application", "scripts", "tools",
               "coherence_bridge", "research"]

RE_OS_SYSTEM = re.compile(r"\bos\.system\s*\(")
RE_YAML_UNSAFE = re.compile(r"\byaml\.load\s*\(")
RE_YAML_SAFE_CALL = re.compile(r"\byaml\.load\s*\([^)]*Loader\s*=\s*[\w.]*SafeLoader")
RE_SHELL_TRUE = re.compile(r"shell\s*=\s*True")
RE_PICKLE_LOAD = re.compile(r"\bpickle\.loads?\s*\(|Unpickler\s*\([^)]*\)\s*\.load\s*\(")


def _iter_py() -> list[Path]:
    # exclude this gate itself: its regex patterns are string literals that would
    # otherwise self-match (a detector must not flag its own detection strings).
    me = Path(__file__).resolve()
    out: list[Path] = []
    for top in FIRST_PARTY:
        d = ROOT / top
        if d.is_dir():
            out.extend(
                p for p in d.rglob("*.py")
                if "/tests/" not in str(p) and p.resolve() != me
            )
    return out


def main() -> int:
    allow = json.loads(ALLOW.read_text()) if ALLOW.exists() else {}
    allow_shell = set(allow.get("shell_true", {}))
    allow_pickle = set(allow.get("pickle_load", {}))

    viol: list[str] = []
    for p in _iter_py():
        rel = str(p.relative_to(ROOT))
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if RE_OS_SYSTEM.search(line):
                viol.append(f"{rel}:{i}  os.system( — forbidden (use subprocess list-argv)")
            if RE_YAML_UNSAFE.search(line) and not RE_YAML_SAFE_CALL.search(line):
                viol.append(f"{rel}:{i}  unsafe yaml.load( — use yaml.safe_load")
        if RE_SHELL_TRUE.search(text) and rel not in allow_shell:
            viol.append(f"{rel}  NEW shell=True site not in allowlist")
        if RE_PICKLE_LOAD.search(text) and rel not in allow_pickle:
            # dump-side (pickle.dump) is fine; only flag load-side that is unallowlisted
            if re.search(r"\bpickle\.loads?\s*\(|Unpickler\s*\([^)]*\)\s*\.load\s*\(", text):
                viol.append(f"{rel}  NEW pickle load site not in allowlist "
                            f"(add a restricted unpickler + allowlist entry)")

    if viol:
        print(f"[-] security-regression gate RED: {len(viol)} new dangerous-primitive site(s) "
              f"vs the SEC-010 baseline:", file=sys.stderr)
        for v in viol:
            print(f"    {v}", file=sys.stderr)
        print("    Remove the primitive, or (if reviewed + genuinely required) add it to "
              ".github/security_regression_allowlist.json with a reason.", file=sys.stderr)
        return 1
    print(f"[+] security-regression gate GREEN: no unallowlisted os.system/unsafe-yaml/"
          f"shell=True/pickle-load in {len(FIRST_PARTY)} first-party trees "
          f"({len(allow_shell)} shell + {len(allow_pickle)} pickle allowlisted).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
