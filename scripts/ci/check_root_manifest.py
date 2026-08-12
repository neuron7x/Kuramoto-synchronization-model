#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab); MIT
"""Release gate G-ROOT-MANIFEST — cold-verify the root ``MANIFEST.sha256``.

This gate is DISTINCT from ``check_manifest_hashes.py`` (gate
G-ARTIFACT-MANIFESTS), which only verifies artifact ``manifest.json`` files
discovered by ``rglob('manifest.json')`` and NEVER covers the root source
manifest. Historically the similar name let a PASS of the artifact gate read as
whole-repo manifest integrity — it never was. This gate closes that semantic
gap: it re-hashes every tracked file and asserts byte-for-byte agreement with
``MANIFEST.sha256`` (0 mismatch, 0 missing, 0 unexpected), failing closed with a
non-zero exit on any drift.

Scope: root source-integrity manifest ONLY. See docs/RELEASE_GATES.md.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_ID = "G-ROOT-MANIFEST"


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/generate_manifest.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    status = "PASS" if proc.returncode == 0 else "FAIL"
    print(f"[{GATE_ID}] root source manifest cold-verify: {status}")
    if proc.returncode != 0:
        print(
            f"[{GATE_ID}] FAIL — root MANIFEST.sha256 drift. This is NOT covered by "
            "G-ARTIFACT-MANIFESTS (check_manifest_hashes.py); regenerate with "
            "scripts/ci/generate_manifest.py and review each diff."
        )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
