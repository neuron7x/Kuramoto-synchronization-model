# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Operator-session ingestion.

Lie blocked:
    "chat insight disappears after session"

Reads a free-form operator-session dump (markdown or text) and emits a
structured engineering-memory record under ``.session_ledger/*.yaml``.
The record captures decisions / accepted_claims / rejected_claims /
PR_numbers / lie_blocked / falsifier / remaining_uncertainty /
next_tasks. The ingester is a *line-pattern parser*, not an LLM
summarizer — it only structures what the dump already states.

Closure rules:
    closure_status=CLOSED requires falsifier to be non-empty
    closure_status=PARTIAL requires remaining_uncertainty to be non-empty

Otherwise the ingestion REJECTS the record (returns INVALID), forcing
the operator to either name the falsifier or downgrade closure.
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

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER_DIR = REPO_ROOT / ".session_ledger"
DEFAULT_OUTPUT = Path("/tmp/geosync_session_ingestion.json")


class IngestionStatus(str, Enum):
    OK_CLOSED = "OK_CLOSED"
    OK_PARTIAL = "OK_PARTIAL"
    OK_BLOCKED = "OK_BLOCKED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    ingested_at: str
    closure_status: str
    decisions: tuple[str, ...]
    accepted_claims: tuple[str, ...]
    rejected_claims: tuple[str, ...]
    pr_numbers: tuple[int, ...]
    lie_blocked: tuple[str, ...]
    falsifier: tuple[str, ...]
    remaining_uncertainty: str
    next_tasks: tuple[str, ...]


@dataclass
class IngestionReport:
    status: IngestionStatus = IngestionStatus.INVALID
    record: SessionRecord | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "record": asdict(self.record) if self.record is not None else None,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# Line-pattern extractors. Each extractor pulls items prefixed by a
# stable header marker. The dump is expected to mark sections with
# "## " or "**LABEL:**"-style headers; extractors are robust to both.
# ---------------------------------------------------------------------------


_SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "decisions": ("decisions", "decision"),
    "accepted_claims": ("accepted_claims", "accepted claims", "accepted"),
    "rejected_claims": ("rejected_claims", "rejected claims", "rejected"),
    "pr_numbers": ("pr_numbers", "pr numbers", "prs", "pull requests"),
    "lie_blocked": ("lie_blocked", "lies blocked", "lie blocked"),
    "falsifier": ("falsifier", "falsifiers"),
    "next_tasks": ("next_tasks", "next tasks", "next"),
}

_KEY_VALUE = re.compile(
    r"^\s*(?:\*\*)?(?P<key>[A-Za-z][A-Za-z_ ]+)(?:\*\*)?\s*:\s*(?P<val>.+?)\s*$"
)
_BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(?P<body>.+?)\s*$")
_HEADER = re.compile(r"^\s*#+\s+(?P<title>.+?)\s*$")


def _section_for_header(title: str) -> str | None:
    title_lower = title.strip().lower().rstrip(":")
    for key, aliases in _SECTION_PATTERNS.items():
        if title_lower in aliases:
            return key
    return None


def _parse_dump(text: str) -> dict[str, Any]:
    sections: dict[str, list[str]] = {k: [] for k in _SECTION_PATTERNS}
    inline: dict[str, str] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m_header = _HEADER.match(line)
        if m_header:
            current = _section_for_header(m_header.group("title"))
            continue
        m_kv = _KEY_VALUE.match(line)
        if m_kv:
            key_norm = m_kv.group("key").strip().lower().replace(" ", "_")
            val = m_kv.group("val").strip()
            inline[key_norm] = val
            # Inline KV form like "Lie blocked: X" also seeds the section.
            section = _section_for_header(m_kv.group("key"))
            if section:
                sections[section].append(val)
                current = None
            continue
        m_bullet = _BULLET.match(line)
        if m_bullet and current is not None:
            sections[current].append(m_bullet.group("body").strip())
            continue
    return {"sections": sections, "inline": inline}


def _extract_pr_numbers(items: Iterable[str]) -> tuple[int, ...]:
    out: list[int] = []
    for item in items:
        for m in re.finditer(r"#?(\d{2,5})", item):
            try:
                n = int(m.group(1))
            except ValueError:
                continue
            if 1 <= n <= 99999:
                out.append(n)
    return tuple(sorted(set(out)))


def _classify_closure(
    closure: str, falsifier: tuple[str, ...], uncertainty: str
) -> IngestionStatus:
    closure_upper = (closure or "").strip().upper()
    if closure_upper == "CLOSED":
        if not falsifier or not any(f.strip() for f in falsifier):
            return IngestionStatus.INVALID
        return IngestionStatus.OK_CLOSED
    if closure_upper == "PARTIAL":
        if not uncertainty.strip():
            return IngestionStatus.INVALID
        return IngestionStatus.OK_PARTIAL
    if closure_upper == "BLOCKED":
        if not uncertainty.strip():
            return IngestionStatus.INVALID
        return IngestionStatus.OK_BLOCKED
    return IngestionStatus.INVALID


def ingest_dump(text: str, *, session_id: str, ingested_at: str) -> IngestionReport:
    parsed = _parse_dump(text)
    sections = parsed["sections"]
    inline = parsed["inline"]

    closure = inline.get("closure_status") or inline.get("closure", "")
    uncertainty = inline.get("remaining_uncertainty", "")

    falsifier = tuple(sections.get("falsifier") or [])
    status = _classify_closure(closure, falsifier, uncertainty)
    if status is IngestionStatus.INVALID:
        report = IngestionReport(status=status)
        if (closure or "").strip().upper() == "CLOSED" and not falsifier:
            report.errors.append("closure=CLOSED but no falsifier section found")
        if (closure or "").strip().upper() in {"PARTIAL", "BLOCKED"} and not uncertainty:
            report.errors.append(f"closure={closure} but remaining_uncertainty empty")
        if not closure:
            report.errors.append("closure_status not stated")
        return report

    record = SessionRecord(
        session_id=session_id,
        ingested_at=ingested_at,
        closure_status=closure.strip().upper(),
        decisions=tuple(sections["decisions"]),
        accepted_claims=tuple(sections["accepted_claims"]),
        rejected_claims=tuple(sections["rejected_claims"]),
        pr_numbers=_extract_pr_numbers(sections["pr_numbers"]),
        lie_blocked=tuple(sections["lie_blocked"]),
        falsifier=falsifier,
        remaining_uncertainty=uncertainty,
        next_tasks=tuple(sections["next_tasks"]),
    )
    return IngestionReport(status=status, record=record)


def write_ledger_entry(report: IngestionReport, ledger_dir: Path) -> Path | None:
    if report.record is None:
        return None
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / f"{report.record.session_id}.yaml"
    payload = {
        "schema_version": 1,
        "status": report.status.value,
        **asdict(report.record),
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest an operator-session dump")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--ingested-at", required=True, help="ISO-8601 timestamp")
    parser.add_argument("--ledger-dir", type=Path, default=DEFAULT_LEDGER_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.input.exists():
        print(f"FAIL: input not found: {args.input}", file=sys.stderr)
        return 1
    text = args.input.read_text(encoding="utf-8")
    report = ingest_dump(text, session_id=args.session_id, ingested_at=args.ingested_at)
    args.output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if report.status is IngestionStatus.INVALID:
        print(f"FAIL: {report.errors}", file=sys.stderr)
        return 1
    write_ledger_entry(report, args.ledger_dir)
    print(f"OK: {report.status.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
