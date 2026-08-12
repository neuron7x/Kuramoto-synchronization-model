#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Release gate G-HERMETIC-IMAGE -- enforce the hermetic-container policy.

Statically validates ``Dockerfile.repro`` (ENV-005) so the reproducible image
cannot silently regress its hermetic guarantees, and asserts the build-provenance
artifact ``artifacts/env/image_digest.json`` exists.

Policy enforced on the Dockerfile text:

  1. Every ``FROM`` pins its base by DIGEST (``@sha256:<64 hex>``), never a
     mutable tag.
  2. A non-root ``USER`` is the effective execution identity (not root / uid 0).
  3. No package-manager mutation at run time: no ``apt-get upgrade``; no
     ``pip install --upgrade`` / ``-U``; any ``apt-get`` layer must clean the
     apt lists (``rm -rf /var/lib/apt/lists``); and ``CMD``/``ENTRYPOINT`` must
     not invoke apt or pip.
  4. Dependencies install with ``pip install --require-hashes`` (pinned+hashed).
  5. Deterministic locale (``C.UTF-8``) and timezone (``UTC``).

Exit codes::

    0  -- Dockerfile satisfies the policy and image_digest.json exists
    1  -- at least one policy violation (fail closed)
    2  -- Dockerfile.repro not found
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_ID = "G-HERMETIC-IMAGE"
DOCKERFILE = ROOT / "Dockerfile.repro"
DIGEST_JSON = ROOT / "artifacts" / "env" / "image_digest.json"

_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}\b")
_ROOT_USERS = {"root", "0", "root:root", "0:0"}


def _logical_instructions(text: str) -> list[str]:
    """Strip comments/blank lines and join backslash-continued Dockerfile lines."""
    instrs: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            # A comment terminates a continuation only if we were not mid-line;
            # heredoc bodies never start with '#', so this is safe here.
            continue
        if buf:
            buf += " " + stripped
        else:
            buf = stripped
        if buf.endswith("\\"):
            buf = buf[:-1].rstrip()
        else:
            instrs.append(buf)
            buf = ""
    if buf:
        instrs.append(buf)
    return instrs


def _by_keyword(instrs: list[str], keyword: str) -> list[str]:
    kw = keyword.upper()
    return [i for i in instrs if i.split(None, 1)[0].upper() == kw]


def check_dockerfile(text: str) -> list[str]:
    """Return a list of policy violations (empty list == compliant)."""
    violations: list[str] = []
    instrs = _logical_instructions(text)
    joined = "\n".join(instrs)

    # 1. digest-pinned base(s)
    froms = _by_keyword(instrs, "FROM")
    if not froms:
        violations.append("no FROM instruction found")
    for f in froms:
        ref = f.split(None, 2)[1] if len(f.split()) > 1 else ""
        if not _DIGEST_RE.search(ref):
            violations.append(f"FROM base not pinned by @sha256 digest: {ref!r}")

    # 2. non-root effective USER
    users = _by_keyword(instrs, "USER")
    if not users:
        violations.append("no USER instruction (would run as root)")
    else:
        effective = users[-1].split(None, 1)[1].strip()
        if effective.lower() in _ROOT_USERS or effective.split(":", 1)[0] in {"root", "0"}:
            violations.append(f"effective USER is root/uid 0: {effective!r}")

    # 3. no runtime package-manager mutation
    if re.search(r"\bapt-get\s+upgrade\b", joined):
        violations.append("apt-get upgrade present (unpinned runtime mutation)")
    if re.search(r"\bpip\b[^\n]*\binstall\b[^\n]*(--upgrade\b|\s-U\b)", joined):
        violations.append("pip install --upgrade/-U present (unpinned mutation)")
    if re.search(r"\bapt(-get)?\b", joined) and "rm -rf /var/lib/apt/lists" not in joined:
        violations.append("apt used without cleaning /var/lib/apt/lists")
    for kw in ("CMD", "ENTRYPOINT"):
        for i in _by_keyword(instrs, kw):
            if re.search(r"\bapt(-get)?\b|\bpip\b", i):
                violations.append(f"{kw} invokes a package manager at run time: {i!r}")

    # 4. hashed dependency install
    if not re.search(r"\bpip\b[^\n]*\binstall\b[^\n]*--require-hashes\b", joined):
        violations.append("no `pip install --require-hashes` (dependencies not hash-pinned)")

    # 5. deterministic locale + timezone
    if not re.search(r"\b(LANG|LC_ALL)=C\.UTF-8\b", joined):
        violations.append("deterministic locale C.UTF-8 not set (LANG/LC_ALL)")
    if not re.search(r"\bTZ=UTC\b", joined):
        violations.append("deterministic timezone TZ=UTC not set")

    return violations


def main() -> int:
    if not DOCKERFILE.exists():
        print(f"[{GATE_ID}] Dockerfile.repro not found at {DOCKERFILE}", file=sys.stderr)
        return 2

    violations = check_dockerfile(DOCKERFILE.read_text(encoding="utf-8"))

    if not DIGEST_JSON.exists():
        violations.append(
            f"build-provenance artifact missing: {DIGEST_JSON.relative_to(ROOT)} "
            "(run scripts/ci/build_hermetic_image.sh)"
        )

    if violations:
        print(f"[{GATE_ID}] FAIL -- hermetic-container policy violated:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print(f"[{GATE_ID}] PASS -- Dockerfile.repro is digest-pinned, non-root, "
          "hash-locked, deterministic; image_digest.json present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
