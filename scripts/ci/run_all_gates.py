#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Whole-tree gate meta-ratchet — run EVERY gate, fail only on NEW red.

Why this exists
---------------
CI is the only thing that runs the gate set, `make verify` is changeset-only, and
no local target runs all ~90 ``check_*`` gates against the full tree. So ratchets
slip and registries desync invisibly (see docs/audit/FRACTAL_HEALTH_MAP_2026-07-21.md).
This runner is the missing whole-tree pass: it executes every gate, classifies the
outcome, and — like every other ratchet in this repo — fails closed on NEW red while
allowlisting the currently-documented red set in ``.github/gate_run_baseline.json``.

Classification
--------------
* GREEN      — exit 0.
* NEEDS_ARGS — exit != 0 but the gate is a changeset/pre-commit hook that requires
               args (``--staged``, ``--base-ref``, ``--now`` …); not a tree defect.
* RED        — exit != 0 with a genuine gate failure.

Exit codes: 0 — no NEW red and no stale baseline entry; 1 — new red or a baseline
entry that is now GREEN (tighten the baseline). Run ``--write`` to re-freeze.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / ".github" / "gate_run_baseline.json"
TIMEOUT = 120

# Inverted tripwire gates: exit != 0 is their HEALTHY state (the guarded-against
# condition did not occur); exit 0 means the tripwire FIRED (a real problem).
_INVERTED = {
    "scripts/ci/check_audit_report_paths.py",  # OK -> return 1; FIRED -> return 0
}

# Runtime watchdogs (cron / systemd sidecars) that probe a LIVE service, not repo
# state. They report UNREACHABLE when no collector is running — an environment
# condition, not a tree defect — so they do not belong in a whole-tree gate sweep.
_EXCLUDE = {
    "scripts/check_l2_collector_health.py",  # docstring: "cron every ~60s, or systemd watchdog sidecar"
}

# Substrings that mark an "I need arguments / a changeset" exit, not a tree defect.
_NEEDS_ARGS = (
    "usage:",
    "the following arguments are required",
    "required unless",
    "expects --staged",
    "--base-ref",
    "base_ref and head_ref",
    "unrecognized arguments",
    "no such option",
)


def _gates() -> list[str]:
    found = sorted(
        rel
        for p in list((ROOT / "scripts" / "ci").glob("check_*.py"))
        + list((ROOT / "scripts").glob("check_*.py"))
        if (rel := p.relative_to(ROOT).as_posix()) not in _EXCLUDE
    )
    return found


def _classify(rel: str) -> tuple[str, str]:
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / rel)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            cwd=ROOT,
        )
    except subprocess.TimeoutExpired:
        return "RED", "timeout"
    if rel in _INVERTED:
        # Inverted: non-zero == healthy, zero == the tripwire fired.
        return ("GREEN", "") if r.returncode != 0 else ("RED", "inverted tripwire FIRED")
    if r.returncode == 0:
        return "GREEN", ""
    blob = (r.stdout + r.stderr).lower()
    if any(m in blob for m in _NEEDS_ARGS):
        return "NEEDS_ARGS", ""
    last = ""
    for line in (r.stdout + r.stderr).splitlines():
        s = line.strip()
        if s and "warning" not in s.lower():
            last = s
    return "RED", last[:120]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="re-freeze the known-red baseline")
    args = ap.parse_args()

    baseline: set[str] = set()
    if BASELINE.exists():
        baseline = set(json.loads(BASELINE.read_text()).get("known_red", []))

    green, needs_args, red = [], [], {}
    for rel in _gates():
        verdict, note = _classify(rel)
        if verdict == "GREEN":
            green.append(rel)
        elif verdict == "NEEDS_ARGS":
            needs_args.append(rel)
        else:
            red[rel] = note

    red_set = set(red)
    new_red = sorted(red_set - baseline)
    healed = sorted(baseline - red_set)  # baseline entry now green → tighten

    print(f"gates: {len(green)+len(needs_args)+len(red)}  "
          f"GREEN={len(green)}  RED={len(red)}  NEEDS_ARGS={len(needs_args)}")
    if red:
        print("RED:")
        for r in sorted(red):
            flag = "NEW" if r in new_red else "known"
            print(f"  [{flag}] {r} :: {red[r]}")

    if args.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {
                    "_doc": "Whole-tree gate meta-ratchet: currently-documented red gates "
                    "(see docs/audit/FRACTAL_HEALTH_MAP). run_all_gates.py fails on NEW red "
                    "or on a listed gate that is now green (tighten). Shrink this set; never "
                    "grow it silently.",
                    "known_red": sorted(red_set),
                },
                indent=2,
            )
            + "\n"
        )
        print(f"wrote baseline: {len(red_set)} known-red")
        return 0

    rc = 0
    if new_red:
        print(f"\nFAIL: {len(new_red)} NEW red gate(s) — a ratchet slipped or a registry "
              f"desynced:\n  " + "\n  ".join(new_red))
        rc = 1
    if healed:
        print(f"\nFAIL: {len(healed)} baseline gate(s) now GREEN — tighten with --write:\n  "
              + "\n  ".join(healed))
        rc = 1
    if rc == 0:
        print("OK: no new red; baseline holds.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
