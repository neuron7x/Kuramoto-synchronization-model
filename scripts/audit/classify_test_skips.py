#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""TST-007 — enumerate and classify every skip/xfail-family marker in tests/.

Deliverable for remediation item TST-007. Extracts each marker with its reason string and
buckets it so the register is not "211 unexplained skips" but a typed inventory:

    dependency-induced   optional dep absent (importorskip / 'not installed' / numpy/torch/ccxt)
    data-artifact-gated  a research data blob (parquet/panel/Askar/csv) is not staged locally
    conditional-inapplicable  scenario does not apply (schema lacks field, nothing to compare)
    env-or-slow-gated    network / live-data / gpu / perf / integration gating
    platform             OS/arch conditional
    by-design-xfail      xfail: a known, documented negative
    todo-wip             explicitly TODO/WIP/pending/flaky — the ones that need action
    unclassified         reason present but not matched — needs a human tag

Only ``todo-wip`` + ``unclassified`` are actionable holes; the rest are legitimate
conditional gating (dependency/data/platform/scenario). A custom marker label such as
``pytestmark = pytest.mark.L3`` is NOT counted — the pytestmark pattern matches only when it
references skip/xfail.

Run: python scripts/audit/classify_test_skips.py [--json]
Exit 0 always (inventory tool, not a gate). The skip-ratchet gate enforces the budget.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATS = {
    "mark.skipif": re.compile(r"@pytest\.mark\.skipif\((.*?)\)", re.S),
    "mark.skip": re.compile(r"@pytest\.mark\.skip\((.*?)\)|@pytest\.mark\.skip\b"),
    "mark.xfail": re.compile(r"@pytest\.mark\.xfail\((.*?)\)|@pytest\.mark\.xfail\b"),
    "pytest.skip": re.compile(r"pytest\.skip\((.*?)\)", re.S),
    "pytest.xfail": re.compile(r"pytest\.xfail\((.*?)\)", re.S),
    "importorskip": re.compile(r"pytest\.importorskip\((.*?)\)", re.S),
    "pytestmark": re.compile(r"pytestmark\s*=\s*(.*(?:skip|xfail).*)"),
}
DEP = re.compile(r"import|installed|module|numpy|torch|ccxt|scipy|pandas|no ndep|dependency|ModuleNotFound", re.I)
ENV = re.compile(r"network|live|real[_ ]?data|gpu|slow|perf|benchmark|integration|redis|socket|binance", re.I)
PLAT = re.compile(r"platform|windows|linux|darwin|sys\.platform|os\.name|arch", re.I)
TODO = re.compile(r"todo|wip|pending|flaky|not implemented|unimplemented|fixme", re.I)
INAPP = re.compile(r"does not declare|nothing to compare|unsupported|not found|required for|only when|single .* present|not available|no .* configured|unspecified|n/a|inapplicable", re.I)
DATA = re.compile(
    r"parquet|panel|not staged|not present|not yet produced|staged|"
    r"data/|\.csv|askar|result file|run .*first|fixture .*(missing|absent)|"
    r"artifact .*(missing|absent|present)",
    re.I,
)


def classify(kind: str, reason: str) -> str:
    if kind == "importorskip":
        return "dependency-induced"
    if kind in {"mark.xfail", "pytest.xfail"} and not TODO.search(reason):
        return "by-design-xfail"
    if TODO.search(reason):
        return "todo-wip"
    if DEP.search(reason):
        return "dependency-induced"
    if PLAT.search(reason):
        return "platform"
    if DATA.search(reason):
        return "data-artifact-gated"
    if INAPP.search(reason):
        return "conditional-inapplicable"
    if ENV.search(reason):
        return "env-or-slow-gated"
    return "unclassified"


def _context(text: str, start: int) -> str:
    """Grab the marker call + a following window so multi-line reasons/conditions are seen."""
    return text[start : start + 240]


def scan() -> tuple[Counter, int, list[dict]]:
    cats: Counter = Counter()
    files: set[str] = set()
    rows: list[dict] = []
    for p in sorted((ROOT / "tests").rglob("*.py")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for kind, pat in PATS.items():
            for m in pat.finditer(text):
                # classify on the whole marker context (condition + reason=), not just group(1) —
                # skipif conditions and reason= kwargs frequently name the actual cause.
                reason = _context(text, m.start())
                cat = classify(kind, reason)
                cats[cat] += 1
                files.add(str(p.relative_to(ROOT)))
                rows.append({"file": str(p.relative_to(ROOT)), "kind": kind, "category": cat})
    return cats, len(files), rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    cats, nfiles, rows = scan()
    total = sum(cats.values())
    if args.json:
        print(json.dumps({"total": total, "files": nfiles, "by_category": dict(cats)}, indent=2))
        return 0
    print(f"TST-007 skip/xfail inventory: {total} markers in {nfiles} files")
    for c, n in cats.most_common():
        print(f"  {c:20} {n}")
    actionable = cats.get("todo-wip", 0) + cats.get("unclassified", 0)
    print(f"\nActionable (todo-wip + unclassified): {actionable} — the rest are "
          f"dependency/env/platform/by-design gating, not silent holes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
