#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Research-claim traceability gate for the docs/phd dissertation layer.

Fail-closed governance that keeps the dissertation honest:

1. **Traceability** — every dissertation chapter must bind to at least one
   verifiable artifact reference (a PR number, a repo path ending .py/.json/.yaml,
   a CI-gate name, or a ledger/falsifier reference). A chapter with empirical-
   looking content but no artifact reference is an *unbound claim* and fails.
2. **No false promotion** — forbidden positive over-claims ("proves", "validates
   market", "profitable", "alpha engine", "B.wheel=0 achieved", "trading edge")
   fail the build UNLESS the line is an explicit negation / non-claim / quoted
   reference (the docs are *allowed* — indeed required — to disclaim these).

Emits ``artifacts/phd_traceability.json``.

Exit codes::
    0  — PASS (every chapter bound; no forbidden positive over-claim)
    1  — FAIL (an unbound claim or a forbidden positive over-claim)
    2  — docs/phd missing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHD_DIR = ROOT / "docs" / "phd"

# An artifact reference: PR number, repo path, gate name, ledger/falsifier token.
ARTIFACT_REF = re.compile(
    r"#\d{2,}"  # PR/issue number
    r"|[\w./-]+\.(?:py|json|yaml|yml)\b"  # repo path
    r"|\b\w+(?:-\w+)*-gate\b"  # CI gate name (foo-bar-gate)
    r"|\brelease-gate\b|\bFALSIFIER_LEDGER\b|\bNEGATIVE_EVIDENCE\b"
    r"|\bbwheel_baseline\b|\bimport_graph\b|\bwheel_contract\b",
)

# Forbidden POSITIVE over-claims (compound, narrow — not bare words).
FORBIDDEN = (
    re.compile(r"\bproves\b", re.IGNORECASE),
    re.compile(r"\bvalidates?\s+(?:the\s+)?market\b", re.IGNORECASE),
    re.compile(r"\bprofitable\b", re.IGNORECASE),
    re.compile(r"\balpha\s+(?:engine|signal|edge|generation)\b", re.IGNORECASE),
    re.compile(r"\btrading\s+edge\b", re.IGNORECASE),
    re.compile(r"\bmarket\s+alpha\b", re.IGNORECASE),
    re.compile(r"\bB\.wheel\s*=\s*0\s+(?:achieved|reached|done|complete)\b", re.IGNORECASE),
    re.compile(r"\bproduction[\s-]+ready\b", re.IGNORECASE),
)

# A line is exempt from the forbidden scan when it is an explicit disclaimer,
# negation, quotation, or non-claim boundary (the docs MUST be able to say
# "makes no profitability claim").
_NEGATION = re.compile(
    r"\b(no|not|never|without|cannot|can't|must not|no claim|non-claim|"
    r"disclaim|forbidden|absent|neither|nor|out[\s-]of[\s-]scope)\b",
    re.IGNORECASE,
)


def _is_exempt(line: str) -> bool:
    if "`" in line or '"' in line:  # quoted / code reference
        return True
    if "NOT" in line or "≠" in line or "NO " in line:
        return True
    return bool(_NEGATION.search(line))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=ROOT / "artifacts" / "phd_traceability.json")
    args = parser.parse_args(argv)

    if not PHD_DIR.is_dir():
        print(f"ERROR: {PHD_DIR.relative_to(ROOT)} missing", file=sys.stderr)
        return 2

    files = sorted(p for p in PHD_DIR.glob("*.md"))
    files_scanned: list[str] = []
    claims_with_artifacts: list[str] = []
    unbound_claims: list[str] = []
    forbidden_terms: list[dict[str, object]] = []

    for path in files:
        rel = str(path.relative_to(ROOT))
        files_scanned.append(rel)
        text = path.read_text(encoding="utf-8")
        if ARTIFACT_REF.search(text):
            claims_with_artifacts.append(rel)
        elif rel.endswith("README.md"):
            claims_with_artifacts.append(rel)  # index is allowed to be a pointer
        else:
            unbound_claims.append(rel)
        for i, line in enumerate(text.splitlines(), 1):
            if _is_exempt(line):
                continue
            for pat in FORBIDDEN:
                if pat.search(line):
                    forbidden_terms.append({"file": rel, "line": i, "match": pat.pattern})

    verdict = "PASS" if not unbound_claims and not forbidden_terms else "FAIL"
    report = {
        "verdict": verdict,
        "files_scanned": files_scanned,
        "claims_with_artifacts": claims_with_artifacts,
        "unbound_claims": unbound_claims,
        "forbidden_terms": forbidden_terms,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for u in unbound_claims:
        print(
            f"UNBOUND CLAIM: {u} has no artifact reference (PR#/path/gate/ledger)", file=sys.stderr
        )
    for f in forbidden_terms:
        print(
            f"FORBIDDEN OVER-CLAIM: {f['file']}:{f['line']} matched /{f['match']}/", file=sys.stderr
        )
    print(
        f"PHD TRACEABILITY: {verdict} — {len(files_scanned)} files, "
        f"{len(claims_with_artifacts)} bound, {len(unbound_claims)} unbound, "
        f"{len(forbidden_terms)} forbidden over-claims"
    )
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
