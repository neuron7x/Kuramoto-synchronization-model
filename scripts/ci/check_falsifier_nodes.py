#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail-closed: every claim falsifier.test_id must resolve to a collectible pytest node.

First principle (a falsifier that cannot be collected cannot fire — it is a test that
cannot fail, the worst kind of silent hole): the ANCHORED-claim falsification contract in
docs/CLAIMS.yaml is only real if each ``falsifier.test_id`` names a test that pytest can
actually COLLECT. Until now this was unenforced: check_claims validates only the string
SHAPE (``::`` present) and defers node-resolution to compute_fps_audit, whose has_test
merely checks whether an evidence_path starts with ``tests/`` — it never reads test_id.
So a falsifier naming a nonexistent node passed every gate.

This gate resolves each falsifier.test_id with ``pytest --collect-only``:

    RESOLVED    node collects              -> OK
    DANGLING    file/node absent or errors -> RED (fail-closed), unless in the allowlist
    ALLOWLISTED collect-gated by a declared optional dependency (documented, not silent)

Allowlist: ``.github/falsifier_node_allowlist.json`` — a {test_id: reason} map for
falsifiers that only collect with an optional dependency installed (e.g. schemathesis).
A new dangling falsifier NOT in the allowlist fails the gate.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAIMS = ROOT / "docs" / "CLAIMS.yaml"
ALLOWLIST = ROOT / ".github" / "falsifier_node_allowlist.json"


def _falsifiers() -> list[tuple[str, str]]:
    import yaml

    data = yaml.safe_load(CLAIMS.read_text(encoding="utf-8"))
    claims = data if isinstance(data, list) else data.get("claims", [])
    out: list[tuple[str, str]] = []
    for c in claims:
        f = c.get("falsifier")
        if isinstance(f, dict) and f.get("test_id"):
            out.append((str(c.get("id")), str(f["test_id"])))
    return out


def _resolves(test_id: str) -> tuple[bool, str]:
    path = test_id.split("::", 1)[0]
    if not (ROOT / path).exists():
        return False, "file missing"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "--no-header", "-o", "addopts=", test_id],
        capture_output=True, text=True, cwd=ROOT, timeout=90,
    )
    if r.returncode == 0:
        return True, "collected"
    last = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()][-1:] or [""]
    return False, f"rc={r.returncode} {last[0][:80]}"


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    allow: dict[str, str] = {}
    if ALLOWLIST.exists():
        allow = json.loads(ALLOWLIST.read_text()).get("allow", {})

    dangling: list[str] = []
    resolved = 0
    allowlisted = 0
    for cid, tid in _falsifiers():
        ok, why = _resolves(tid)
        if ok:
            resolved += 1
        elif tid in allow:
            allowlisted += 1
        else:
            dangling.append(f"{cid}: {tid} — {why}")

    total = resolved + allowlisted + len(dangling)
    if dangling:
        print(f"[-] falsifier-node gate RED: {len(dangling)} falsifier(s) name an "
              f"unresolvable pytest node (a falsifier that cannot fire):", file=sys.stderr)
        for d in dangling:
            print(f"    {d}", file=sys.stderr)
        print("    Fix the test_id, or add it to .github/falsifier_node_allowlist.json "
              "with a reason if it is optional-dependency-gated.", file=sys.stderr)
        return 1
    print(f"[+] falsifier-node gate GREEN: {resolved}/{total} falsifiers resolve to a "
          f"collectible pytest node ({allowlisted} allowlisted optional-dep).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
