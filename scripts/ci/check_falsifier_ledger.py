# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate over governance/FALSIFIER_LEDGER.yaml.

A falsifier (null model, kill-test, integrity check) is only worth anything if
it is *executable*: real code that exists in the tree and a test that exercises
it. This gate refuses to let a falsifier silently rot into prose. For every
entry it verifies that:

  * the entry declares an allowed ``kind``;
  * its ``impl_file`` exists and defines its declared ``symbol``;
  * its ``test_file`` exists (the executable witness); and
  * it carries a non-empty ``description``.

On ``--json`` it emits a machine-readable ledger of the resolved status of each
falsifier so the release gate (probe ``H.falsification``) can consume it.

Exit codes:
    0  — every falsifier resolves (impl + symbol + test present)
    1  — at least one falsifier is missing, renamed, or has no witness
    2  — the ledger file is absent or malformed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "governance" / "FALSIFIER_LEDGER.yaml"

ALLOWED_KINDS = frozenset({"null_model", "falsifier", "integrity"})
REQUIRED_FIELDS = ("id", "kind", "impl_file", "symbol", "test_file", "description")


def _symbol_defined(path: Path, symbol: str) -> bool:
    """Return True if *symbol* is defined (def/class/assignment) in *path*."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^\s*(?:async\s+def|def|class)\s+{re.escape(symbol)}\b"
        rf"|^\s*{re.escape(symbol)}\s*[:=]",
        re.MULTILINE,
    )
    return bool(pattern.search(text))


def _check_entry(entry: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (status, problems) for a single ledger entry.

    status is one of: RESOLVED, BROKEN, MALFORMED.
    """
    problems: list[str] = []

    missing = [f for f in REQUIRED_FIELDS if not str(entry.get(f, "")).strip()]
    if missing:
        return "MALFORMED", [f"missing field(s): {', '.join(missing)}"]

    kind = str(entry["kind"])
    if kind not in ALLOWED_KINDS:
        problems.append(f"kind {kind!r} not in {sorted(ALLOWED_KINDS)}")

    impl = ROOT / str(entry["impl_file"])
    if not impl.is_file():
        problems.append(f"impl_file missing: {entry['impl_file']}")
    elif not _symbol_defined(impl, str(entry["symbol"])):
        problems.append(f"symbol {entry['symbol']!r} not defined in {entry['impl_file']}")

    test = ROOT / str(entry["test_file"])
    if not test.is_file():
        problems.append(f"test_file (witness) missing: {entry['test_file']}")

    return ("RESOLVED" if not problems else "BROKEN"), problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="write the machine-readable resolved ledger to this path",
    )
    args = parser.parse_args(argv)

    if not LEDGER.is_file():
        print(f"FALSIFIER LEDGER: missing {LEDGER.relative_to(ROOT)}", file=sys.stderr)
        return 2

    try:
        data = yaml.safe_load(LEDGER.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        print(f"FALSIFIER LEDGER: malformed YAML: {exc}", file=sys.stderr)
        return 2

    if not isinstance(data, dict) or not isinstance(data.get("falsifiers"), list):
        print("FALSIFIER LEDGER: top-level 'falsifiers' list required", file=sys.stderr)
        return 2

    falsifiers: list[dict[str, Any]] = data["falsifiers"]
    if not falsifiers:
        print("FALSIFIER LEDGER: ledger is empty", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    ok = True
    for entry in falsifiers:
        if not isinstance(entry, dict):
            print("FALSIFIER LEDGER: non-mapping entry", file=sys.stderr)
            return 2
        fid = str(entry.get("id", "<no-id>"))
        status, problems = _check_entry(entry)
        if fid in seen:
            status, problems = "BROKEN", [*problems, f"duplicate id: {fid}"]
        seen.add(fid)
        if status != "RESOLVED":
            ok = False
            for p in problems:
                print(f"FALSIFIER LEDGER [{fid}]: {p}", file=sys.stderr)
        results.append(
            {
                "id": fid,
                "kind": entry.get("kind"),
                "impl_file": entry.get("impl_file"),
                "symbol": entry.get("symbol"),
                "test_file": entry.get("test_file"),
                "blocks_promotion": bool(entry.get("blocks_promotion", False)),
                "status": status,
            }
        )

    resolved = sum(1 for r in results if r["status"] == "RESOLVED")
    summary = {
        "schema_version": data.get("schema_version"),
        "total": len(results),
        "resolved": resolved,
        "verdict": "GREEN" if ok else "RED",
        "falsifiers": results,
    }
    if args.json is not None:
        args.json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(
        f"FALSIFIER LEDGER: {resolved}/{len(results)} executable falsifiers resolved"
        f" — {'GREEN' if ok else 'RED'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
