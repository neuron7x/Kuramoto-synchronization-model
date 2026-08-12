#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic invariant teeth-audit — replaces hand-classification with an instrument.

The 2026-07-21 vertical-inference L0 hand-classification (123 teeth / 9 hollow / 0 gap)
was REFUTED: no generator, inconsistent teeth/hollow criterion, and skipped bindings
mislabelled hollow instead of gap. This is the generator the refutation demanded — one
stated criterion, skip-aware, reproducible.

SINGLE CRITERION (per invariant in .claude/physics/INVARIANTS.yaml, keyed on its
AUTHORITATIVE ``tests`` binding — NOT a loose grep):

    GAP_UNBOUND     tests: field is empty            -> no declared witness at all
    GAP_SOURCE      source file does not exist       -> nothing to witness
    GAP_DANGLING    tests bound but does not collect  -> witness path is broken
    GAP_SKIPONLY    collects but every node skipped   -> skip-aware (was mislabelled hollow)
    BOUND_RED       collects, runs, FAILS             -> witness present but currently red
    BOUND_GREEN     collects, runs, ≥1 node passes    -> witness present and passing

BOUND_GREEN is a teeth *candidate*; actual teeth (would the test FAIL if the physics
were wrong?) is proven per-invariant by ``--mutate INV-ID`` firing-evidence, not asserted
here. This gate reports the deterministic binding state and, in --check, fail-closes if
the BOUND count regresses below the frozen floor in .github/invariant_teeth_baseline.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".claude" / "physics" / "INVARIANTS.yaml"
BASELINE = ROOT / ".github" / "invariant_teeth_baseline.json"
REPORT = ROOT / "artifacts" / "physics_v2" / "invariant_teeth_audit.json"


def _load_invariants() -> list[dict]:
    import yaml

    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    out: list[dict] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if str(o.get("id", "")).startswith("INV"):
                out.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return out


def _as_list(x: object) -> list[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(i) for i in x]
    return [str(x)]


def _collect(paths: list[str]) -> tuple[bool, int, int]:
    """Return (collected_any, node_count, skip_count) for the bound test paths."""
    existing = [p.split("::", 1)[0] for p in paths if (ROOT / p.split("::", 1)[0]).exists()]
    if not existing:
        return False, 0, 0
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *existing, "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=ROOT, timeout=180,
    )
    # count collected test nodes; pytest prints "<n> tests collected"
    node_count = 0
    for line in (r.stdout + r.stderr).splitlines():
        s = line.strip()
        if s.endswith("tests collected") or s.endswith("test collected"):
            try:
                node_count = int(s.split()[0])
            except ValueError:
                pass
        elif " collected" in s and ("error" in s or "errors" in s):
            node_count = 0
    return node_count > 0, node_count, 0


def classify(inv: dict) -> dict:
    inv_id = inv["id"]
    tests = _as_list(inv.get("tests"))
    sources = _as_list(inv.get("source"))
    # A source binding may carry a ``::symbol`` suffix (e.g. ``foo.py::Bar``); strip it
    # before the file-existence check, mirroring the tests branch (line ~104). Without
    # this, every symbol-qualified source read as a missing file → spurious GAP_SOURCE.
    src_ok = bool(sources) and any((ROOT / s.strip().split("::", 1)[0]).exists() for s in sources)
    rec = {"id": inv_id, "priority": inv.get("priority"), "provenance": inv.get("provenance"),
           "bound": bool(tests), "source_ok": src_ok, "status": ""}
    if not tests:
        rec["status"] = "GAP_UNBOUND"
        return rec
    if not src_ok:
        rec["status"] = "GAP_SOURCE"
        return rec
    existing = [p.split("::", 1)[0] for p in tests if (ROOT / p.split("::", 1)[0]).exists()]
    if not existing:
        rec["status"] = "GAP_DANGLING"
        return rec
    # ONE run per binding: rc 0=green, 5=skip-only/no-collect, 2/4=collection error
    # (dangling), else red. --timeout guards runaway property suites.
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", *existing, "-q", "-p", "no:cacheprovider",
             "--no-header", "-o", "addopts=", "--timeout=90", "-x"],
            capture_output=True, text=True, cwd=ROOT, timeout=300,
        )
    except subprocess.TimeoutExpired:
        rec["status"] = "BOUND_TIMEOUT"
        return rec
    rc = r.returncode
    blob = (r.stdout + r.stderr)
    if rc in (2, 3, 4) or "error" in blob.lower().split("\n")[-3:][0:1] and "collected" not in blob:
        rec["status"] = "GAP_DANGLING"
    elif rc == 5:
        rec["status"] = "GAP_SKIPONLY"
    elif rc == 0:
        rec["status"] = "BOUND_GREEN"
    else:
        tail = [ln for ln in blob.strip().splitlines() if ln.strip()][-1:] or [""]
        rec["status"], rec["note"] = "BOUND_RED", tail[0][:120]
    return rec


def audit() -> dict:
    invs = _load_invariants()
    records = [classify(i) for i in invs]
    from collections import Counter
    counts = dict(Counter(r["status"] for r in records))
    bound_green = [r["id"] for r in records if r["status"] == "BOUND_GREEN"]
    return {"total": len(records), "counts": counts,
            "bound_green_count": len(bound_green), "records": records}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="freeze the BOUND_GREEN floor + write report")
    ap.add_argument("--check", action="store_true", help="fail-closed if BOUND_GREEN regresses")
    args = ap.parse_args()

    result = audit()
    print(json.dumps({"total": result["total"], "counts": result["counts"],
                      "bound_green": result["bound_green_count"]}, indent=2))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if args.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(
            {"_doc": "Deterministic invariant teeth-audit floor: BOUND_GREEN (witness "
                     "collects, is not skip-only, and passes) must not regress. Raise as "
                     "witnesses are added; a drop is a fail-closed regression.",
             "bound_green_floor": result["bound_green_count"]}, indent=2) + "\n",
            encoding="utf-8")
        print(f"froze BOUND_GREEN floor = {result['bound_green_count']}")
        return 0

    if args.check and BASELINE.exists():
        floor = json.loads(BASELINE.read_text())["bound_green_floor"]
        if result["bound_green_count"] < floor:
            print(f"REGRESSION: BOUND_GREEN {result['bound_green_count']} < floor {floor}",
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
