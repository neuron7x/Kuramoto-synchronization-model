#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical-counts reconciliation artifact — one source for every headline number.

The 2026-07 external assessment found four count drifts between report prose
and live gates (test files 1746 vs 1833, manifest entries 7007 vs 7014,
invariants 129 vs 132, claim surfaces 623 vs 660). Each number was true at a
different commit; none was wrong, but no artifact said which commit each was
true AT. This probe removes that failure class: every headline count is
recomputed here from the same authoritative source its gate uses, stamped with
the git SHA, and written to one artifact. A report that cites a count without
citing this artifact (or regenerating it) is citing hearsay.

Usage::

    python -m scripts.ci.canonical_counts            # write + print
    python -m scripts.ci.canonical_counts --verify   # fail if artifact is stale

Exit codes: 0 — written/verified; 1 — --verify found drift vs the live tree.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "artifacts" / "release_gate" / "canonical_counts.json"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def _tracked_files() -> list[str]:
    return [line for line in _git("ls-files").splitlines() if line]


def count_test_files() -> int:
    """Same rule as release_gate probe P.tests."""
    return sum(1 for rel in _tracked_files() if "/test_" in f"/{rel}" and rel.endswith(".py"))


def count_manifest_entries() -> int:
    path = ROOT / "MANIFEST.sha256"
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def count_invariants() -> int:
    """Same source as scripts/count_invariants.py (the registry single source)."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "count_invariants.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return int(proc.stdout.strip().splitlines()[-1])


def count_claim_surfaces() -> int:
    """Same enumeration as check_claim_boundary's canonical surface walk."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_claim_boundary", ROOT / "scripts" / "ci" / "check_claim_boundary.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass introspection needs the module registered
    spec.loader.exec_module(mod)
    return len(list(mod._iter_surface()))


def build() -> dict[str, object]:
    return {
        "_doc": (
            "Canonical headline counts, each recomputed from the same source its "
            "gate uses, at the stamped commit. Reports must cite this artifact, "
            "not remembered numbers."
        ),
        "git_sha": _git("rev-parse", "HEAD").strip(),
        "counts": {
            "test_files_tracked": {
                "value": count_test_files(),
                "source": "git ls-files, rule of release_gate probe P.tests",
            },
            "manifest_entries": {
                "value": count_manifest_entries(),
                "source": "MANIFEST.sha256 line count (gate D.manifest input)",
            },
            "invariants": {
                "value": count_invariants(),
                "source": "scripts/count_invariants.py (.claude/physics/INVARIANTS.yaml)",
            },
            "claim_surfaces": {
                "value": count_claim_surfaces(),
                "source": "check_claim_boundary._iter_surface (gate scan set)",
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical-counts reconciliation artifact.")
    parser.add_argument("--verify", action="store_true", help="fail if artifact drifted")
    args = parser.parse_args(argv)

    live = build()
    if args.verify:
        if not ARTIFACT.is_file():
            print("canonical_counts.json absent — regenerate it")
            return 1
        stored = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        stored_counts = {k: v["value"] for k, v in stored.get("counts", {}).items()}
        live_counts = {k: v["value"] for k, v in live["counts"].items()}
        if stored_counts != live_counts:
            for key in sorted(live_counts):
                if stored_counts.get(key) != live_counts[key]:
                    print(f"DRIFT: {key} stored={stored_counts.get(key)} live={live_counts[key]}")
            return 1
        print(f"canonical counts verified at {stored.get('git_sha', '?')[:12]}: {live_counts}")
        return 0

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(live, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v["value"] for k, v in live["counts"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
