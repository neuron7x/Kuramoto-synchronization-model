# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Complexity-pressure meter — proof-to-ceremony ratio.

Lie blocked:
    "more validation code always improves truth"

Counts code/governance/test concentration and reports a band:

    HEALTHY            evidence and validation are proportional to runtime
    CEREMONY_RISK      governance / docs grow but tests / falsifiers do not
    UNDERTESTED        runtime grows but tests do not
    OVERVALIDATED      validators outnumber claims they could falsify
    UNKNOWN            inputs degenerate (empty repo, unreadable files)

The meter does NOT emit a score. Bands only. The lie blocked is
specifically the "score = truth" trap; presenting `validation_density:
0.847` is the same lie this module refuses.

Inputs are pure file scans against the working tree. The meter is
stdlib-only and deterministic in its file ordering.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("/tmp/geosync_complexity_pressure.json")


class PressureBand(str, Enum):
    HEALTHY = "HEALTHY"
    CEREMONY_RISK = "CEREMONY_RISK"
    UNDERTESTED = "UNDERTESTED"
    OVERVALIDATED = "OVERVALIDATED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Metrics:
    runtime_loc: int
    governance_loc: int
    test_loc: int
    validator_count: int
    claims_count: int
    falsifier_count: int
    executable_gate_count: int
    generated_doc_loc: int
    hand_maintained_doc_loc: int


@dataclass
class PressureReport:
    band: PressureBand = PressureBand.UNKNOWN
    metrics: Metrics | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "band": self.band.value,
            "metrics": asdict(self.metrics) if self.metrics is not None else None,
            "reasons": list(self.reasons),
        }


_RUNTIME_DIRS = (
    "geosync_hpc",
    "geosync",
    "core",
    "execution",
    "application",
    "src",
)
_GOVERNANCE_DIRS = (
    "tools/governance",
    "tools/audit",
    "tools/research",
    "tools/deps",
    "tools/mutation",
    ".claude",
)
_TEST_DIRS = ("tests",)
_DOC_DIRS = ("docs",)


def _count_loc(repo_root: Path, prefixes: Iterable[str]) -> int:
    total = 0
    for prefix in prefixes:
        base = repo_root / prefix
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                total += sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError):
                continue
    return total


def _count_md_loc(repo_root: Path, prefix: str, *, generated: bool) -> int:
    base = repo_root / prefix
    if not base.exists():
        return 0
    total = 0
    for path in base.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        is_generated = bool(re.search(r"<!--\s*generated\s*-->", text.lower()))
        if is_generated == generated:
            total += sum(1 for _ in text.splitlines())
    return total


def _count_validators(repo_root: Path) -> int:
    count = 0
    for prefix in _GOVERNANCE_DIRS:
        base = repo_root / prefix
        if not base.exists():
            continue
        for path in base.rglob("validate_*.py"):
            if "__pycache__" in path.parts:
                continue
            count += 1
    return count


def _count_claims(repo_root: Path) -> int:
    """Count entries in CLAIMS.yaml (best-effort; 0 if absent or unreadable)."""
    p = repo_root / ".claude" / "claims" / "CLAIMS.yaml"
    if not p.exists():
        return 0
    try:
        import yaml

        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return 0
    if isinstance(data, dict):
        for key in ("claims", "entries", "ledger"):
            block = data.get(key)
            if isinstance(block, list):
                return len(block)
    if isinstance(data, list):
        return len(data)
    return 0


def _count_falsifier_text(repo_root: Path) -> int:
    """Count `_FALSIFIER_TEXT` constants across the runtime + governance trees."""
    count = 0
    for prefix in (*_RUNTIME_DIRS, *_GOVERNANCE_DIRS):
        base = repo_root / prefix
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "_FALSIFIER_TEXT" in text:
                count += 1
    return count


def _count_executable_gates(repo_root: Path) -> int:
    """Count CI workflows whose YAML body invokes a `validate_*.py` script."""
    wf_dir = repo_root / ".github" / "workflows"
    if not wf_dir.exists():
        return 0
    count = 0
    for path in wf_dir.rglob("*.yml"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"validate_[a-z0-9_]+\.py", text):
            count += 1
    return count


def collect_metrics(repo_root: Path) -> Metrics:
    return Metrics(
        runtime_loc=_count_loc(repo_root, _RUNTIME_DIRS),
        governance_loc=_count_loc(repo_root, _GOVERNANCE_DIRS),
        test_loc=_count_loc(repo_root, _TEST_DIRS),
        validator_count=_count_validators(repo_root),
        claims_count=_count_claims(repo_root),
        falsifier_count=_count_falsifier_text(repo_root),
        executable_gate_count=_count_executable_gates(repo_root),
        generated_doc_loc=_count_md_loc(repo_root, _DOC_DIRS[0], generated=True),
        hand_maintained_doc_loc=_count_md_loc(repo_root, _DOC_DIRS[0], generated=False),
    )


def classify(metrics: Metrics) -> tuple[PressureBand, list[str]]:
    """Pure band classifier. Bands only — no numeric score escapes.

    Decision rules (first match wins):

      UNKNOWN
        runtime + governance + test all zero (degenerate input).

      UNDERTESTED
        runtime > 1000 LoC AND test < runtime / 4 (less than 25% test
        coverage by LoC ratio).

      OVERVALIDATED
        validator_count > max(1, claims_count) AND
        falsifier_count < validator_count.
        (More validators than claims they could falsify.)

      CEREMONY_RISK
        hand_maintained_doc_loc > test_loc AND test_loc > 0.
        (Documentation grows faster than the test surface.)

      HEALTHY
        otherwise.
    """
    reasons: list[str] = []
    if metrics.runtime_loc + metrics.governance_loc + metrics.test_loc == 0:
        reasons.append("degenerate: all major LoC counts are zero")
        return PressureBand.UNKNOWN, reasons

    if metrics.runtime_loc > 1000 and metrics.test_loc < metrics.runtime_loc // 4:
        reasons.append(
            f"runtime_loc={metrics.runtime_loc} but test_loc={metrics.test_loc} (< 25% of runtime)"
        )
        return PressureBand.UNDERTESTED, reasons

    if (
        metrics.validator_count > max(1, metrics.claims_count)
        and metrics.falsifier_count < metrics.validator_count
    ):
        reasons.append(
            f"validator_count={metrics.validator_count} exceeds claims_count="
            f"{metrics.claims_count} and falsifier_count={metrics.falsifier_count}"
        )
        return PressureBand.OVERVALIDATED, reasons

    if metrics.hand_maintained_doc_loc > metrics.test_loc and metrics.test_loc > 0:
        reasons.append(
            f"hand_maintained_doc_loc={metrics.hand_maintained_doc_loc} "
            f"> test_loc={metrics.test_loc}"
        )
        return PressureBand.CEREMONY_RISK, reasons

    reasons.append("evidence and validation are proportional to runtime")
    return PressureBand.HEALTHY, reasons


def assess(repo_root: Path = REPO_ROOT) -> PressureReport:
    metrics = collect_metrics(repo_root)
    band, reasons = classify(metrics)
    return PressureReport(band=band, metrics=metrics, reasons=reasons)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure complexity pressure")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = assess(args.repo_root)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    print(f"OK: band={report.band.value}", file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
