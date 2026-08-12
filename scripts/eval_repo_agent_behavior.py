#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""External-agent behavioural eval — surface-encoding harness (Task 7).

The repository must be evaluated as an INFERENCE object: an external agent
(Copilot / Claude Code / Codex / RAG / reviewer) reading the canonical surface
should reconstruct the right claims, boundaries and next actions — and must NOT
be able to assert a forbidden claim. A full live-LLM eval is non-deterministic
and API-gated (a separate follow-up); this harness is its deterministic,
CI-runnable core: for each case it verifies the canonical SURFACE the agent
reads (a) ENCODES the ground-truth answer (expected phrases in the cited files)
and (b) does NOT carry the adversarial forbidden phrase as an endorsed claim.

If the surface fails to encode the truth, or carries a forbidden phrase, an
agent cannot honestly answer — the repo is not inference-ready and the gate
fails.

Usage::

    python scripts/eval_repo_agent_behavior.py [--cases evals/repo_agent_eval_cases.jsonl]

Exit codes: 0 every case passes; 1 at least one case fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evals" / "repo_agent_eval_cases.jsonl"
OUT_DIR = ROOT / "artifacts" / "repo_agent_eval"


def _read(root: Path, rel: str) -> str | None:
    p = root / rel
    return p.read_text(encoding="utf-8") if p.is_file() else None


def evaluate_case(case: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """Pure: return a verdict for one case against the on-disk surface."""
    missing: list[str] = []

    for rel in case.get("required_file_refs", []):
        if not (root / rel).is_file():
            missing.append(f"missing required file: {rel}")

    for rel, phrase in case.get("expect_in", []):
        text = _read(root, rel)
        if text is None:
            missing.append(f"expect_in file absent: {rel}")
        elif phrase not in text:
            missing.append(f"surface does not encode {phrase!r} in {rel}")

    for cmd in case.get("required_commands", []):
        if not any(cmd in (_read(root, rel) or "") for rel in case.get("required_file_refs", [])):
            missing.append(f"required command {cmd!r} not referenced in cited files")

    # Forbidden phrases must NOT appear in the cited surface files (an agent
    # reading them could otherwise quote the forbidden claim as endorsed).
    forbidden_hits: list[str] = []
    surface_files = case.get("required_file_refs", []) + [f for f, _ in case.get("expect_in", [])]
    for phrase in case.get("forbidden_phrases", []):
        for rel in set(surface_files):
            if phrase in (_read(root, rel) or ""):
                forbidden_hits.append(f"forbidden phrase {phrase!r} present in {rel}")

    passed = not missing and not forbidden_hits
    return {
        "id": case.get("id", "<no-id>"),
        "passed": passed,
        "missing": missing,
        "forbidden_hits": forbidden_hits,
    }


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def run(cases: list[dict[str, Any]], root: Path = ROOT) -> dict[str, Any]:
    verdicts = [evaluate_case(c, root) for c in cases]
    failed = [v for v in verdicts if not v["passed"]]
    return {
        "schema": "repo_agent_eval@v1",
        "case_count": len(verdicts),
        "pass_count": len(verdicts) - len(failed),
        "fail_count": len(failed),
        "all_passed": not failed,
        "verdicts": verdicts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--no-write", action="store_true", help="do not persist artifacts")
    args = parser.parse_args(argv)

    report = run(load_cases(args.cases))
    if not args.no_write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"repo-agent eval: {report['pass_count']}/{report['case_count']} cases passed")
    for v in report["verdicts"]:
        if not v["passed"]:
            for m in v["missing"] + v["forbidden_hits"]:
                print(f"  [{v['id']}] {m}", file=sys.stderr)
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
